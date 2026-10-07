#!/usr/bin/env python3
"""
Wikidata Enrichment — free, no API key required.
================================================
For each company in the pipeline, looks up Wikidata and records:
founded year, country, industry, official website. Conservative matching:
only enriches when the top search result is clearly a business entity.

Run:
  python3 scripts/enrich.py              # enrich all missing
  python3 scripts/enrich.py --limit 20   # just 20 (for testing)

Intended to run weekly via .github/workflows/enrich.yml.
Writes to the `enrichment` table in data.db.
"""
import argparse
import json
import re
import sqlite3
import time
import urllib.parse
import urllib.request
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, "data.db")
UA = "MisoListsBot/1.0 (+https://github.com/MisoPrettyStacks/MisoLists.io; contact via repo)"
API = "https://www.wikidata.org/w/api.php"

# Wikidata "instance of" values that mean "this is a business/company"
BUSINESS_TYPES = {
    "Q4830453",  # business
    "Q6881511",  # enterprise
    "Q891723",   # public company
    "Q783794",   # company
    "Q156839",   # startup company (rarely used, but just in case)
}

# description keywords that scream "company" (Wikidata descriptions are short
# and reliable, e.g. "financial technology company", "British online bank")
BUSINESS_HINTS = {
    "company", "bank", "startup", "fintech", "financial technology",
    "manufacturer", "enterprise", "corporation", "business",
    "airline", "retailer", "unicorn", "venture",
}


def api(params):
    params = dict(params, format="json")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def search_company(name):
    """Return Wikidata QID of the best business-entity match, or None."""
    try:
        res = api({"action": "wbsearchentities", "search": name,
                   "language": "en", "limit": 10})
    except Exception:
        return None
    for hit in res.get("search", []):
        qid = hit.get("id")
        desc = (hit.get("description") or "").lower()
        # quick reject: clearly not a company
        if any(w in desc for w in ["song", "album", "film", "novel", "video game",
                                    "football", "given name", "surname"]):
            continue
        ok, signal = is_business(qid, desc)
        if ok:
            return qid, signal
    return None, None


_entity_cache = {}

def get_entity(qid):
    if qid not in _entity_cache:
        try:
            res = api({"action": "wbgetentities", "ids": qid,
                       "props": "claims|labels", "languages": "en"})
            _entity_cache[qid] = res.get("entities", {}).get(qid, {})
        except Exception:
            _entity_cache[qid] = {}
        time.sleep(0.4)  # be nice to the API
    return _entity_cache[qid]


def is_business(qid, desc=""):
    """Returns (is_business, signal_strength). Signal is 'p31' (strong),
    'desc' (medium), 'fallback' (weak) — stored so downstream consumers
    know how much to trust the match."""
    # fast path: Wikidata's own short description says it's a company
    if any(h in desc.lower() for h in BUSINESS_HINTS):
        return True, "desc"
    ent = get_entity(qid)
    claims = ent.get("claims", {})
    for stmt in claims.get("P31", []):  # instance of
        try:
            v = stmt["mainsnak"]["datavalue"]["value"]["id"]
            if v in BUSINESS_TYPES:
                return True, "p31"
        except (KeyError, TypeError):
            pass
    # fallback: has an inception date plus org signals (industry/website/country)
    if "P571" in claims and any(p in claims for p in ("P452", "P856", "P17")):
        return True, "fallback"
    return False, None


def claim_year(ent, prop):
    try:
        v = ent["claims"][prop][0]["mainsnak"]["datavalue"]["value"]["time"]
        m = re.match(r"^[+-]?(\d{4})", v)
        return int(m.group(1)) if m else None
    except (KeyError, IndexError, TypeError):
        return None


def claim_label(ent, prop):
    """Resolve the English label of the first entity-valued claim."""
    try:
        qid = ent["claims"][prop][0]["mainsnak"]["datavalue"]["value"]["id"]
    except (KeyError, IndexError, TypeError):
        return None
    tgt = get_entity(qid)
    try:
        return tgt["labels"]["en"]["value"]
    except KeyError:
        return None


def claim_url(ent, prop="P856"):
    try:
        return ent["claims"][prop][0]["mainsnak"]["datavalue"]["value"]
    except (KeyError, IndexError, TypeError):
        return None


def enrich_one(name):
    qid, signal = search_company(name)
    if not qid:
        return {"wikidata_id": None}
    ent = get_entity(qid)
    return {
        "wikidata_id": qid,
        "match_signal": signal,
        "founded_year": claim_year(ent, "P571"),   # inception
        "country": claim_label(ent, "P17") or claim_label(ent, "P495"),
        "industry": claim_label(ent, "P452"),
        "website": claim_url(ent),
        "defunct": 1 if "P576" in ent.get("claims", {}) else 0,  # dissolved
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    db = sqlite3.connect(DB_PATH)
    # schema migration for the match_signal column
    ecols = [r[1] for r in db.execute("PRAGMA table_info(enrichment)").fetchall()]
    if ecols and "match_signal" not in ecols:
        print("[enrich] migrating enrichment schema (adding match_signal)...")
        db.execute("DROP TABLE IF EXISTS enrichment")
    db.execute("""
        CREATE TABLE IF NOT EXISTS enrichment (
            company TEXT PRIMARY KEY, norm TEXT, wikidata_id TEXT,
            match_signal TEXT, founded_year INT, country TEXT, industry TEXT,
            website TEXT, defunct INT DEFAULT 0, enriched_at TEXT)
    """)
    done = {r[0] for r in db.execute("SELECT company FROM enrichment WHERE wikidata_id IS NOT NULL")}
    companies = [r[0] for r in db.execute("SELECT company FROM pipeline")]
    todo = [c for c in companies if c not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"[enrich] {len(todo)} companies to enrich ({len(done)} already done)")

    import datetime
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    n_ok = 0
    for i, name in enumerate(todo):
        try:
            info = enrich_one(name)
        except Exception as e:
            print(f"  [{i+1}/{len(todo)}] {name}: ERROR {e}")
            info = {"wikidata_id": None}
        db.execute(
            "INSERT OR REPLACE INTO enrichment(company,wikidata_id,match_signal,founded_year,country,industry,website,defunct,enriched_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (name, info.get("wikidata_id"), info.get("match_signal"), info.get("founded_year"),
             info.get("country"), info.get("industry"), info.get("website"),
             info.get("defunct", 0), ts))
        if info.get("wikidata_id"):
            n_ok += 1
            print(f"  [{i+1}/{len(todo)}] {name} -> {info['wikidata_id']} "
                  f"({info.get('founded_year')}, {info.get('country')})")
        if (i + 1) % 25 == 0:
            db.commit()
        time.sleep(0.6)  # rate limit
    db.commit()
    print(f"[enrich] DONE. enriched {n_ok}/{len(todo)}")


if __name__ == "__main__":
    main()
