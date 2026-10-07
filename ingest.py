#!/usr/bin/env python3
"""
Strategic Investment Pipeline — Autonomous Ingestion Engine (GitHub Pages edition)
===============================================================================
Runs locally and in GitHub Actions. Reads every file in ./reports, SHA-256
dedupes, parses xlsx + pdf, merges the two tracker views by company, rebuilds
the SQLite database (data.db) with full source lineage, and regenerates the
dashboard data bundle (assets/data.js). GitHub Pages auto-rebuilds from the
committed assets/data.js.

Run:
  python3 ingest.py            # default: ./reports  (repo-relative)
  python3 ingest.py <folder>   # any folder of xlsx/pdf reports

Triggered automatically by .github/workflows/ingest.yml on every push to
reports/** and on a daily schedule — fully free on GitHub Actions.
"""
import openpyxl, json, os, sqlite3, hashlib, sys, glob, re
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
SITE_DATA = os.path.join(BASE, "assets", "data.js")
DB_PATH = os.path.join(BASE, "data.db")
DEFAULT_FOLDER = os.path.join(BASE, "reports")

def now(): return datetime.now(timezone.utc).isoformat()

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()

def sheet_rows(ws):
    return [[c for c in r] for r in ws.iter_rows(values_only=True)]

def load_xlsx(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    return {sn: sheet_rows(wb[sn]) for sn in wb.sheetnames}

def load_pdf(path):
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(path) as pdf:
            for pg in pdf.pages:
                pages.append(pg.extract_text() or "")
        return {"pages": len(pages), "text": "\n\n".join(pages)}
    except Exception as e:
        return {"pages": 0, "text": "", "error": str(e)}

def num(v):
    if v is None or v == "": return None
    try: return float(v)
    except: return None

# ---------------------------------------------------------------------------
# Data-quality layer (audit 2026-10-06)
# The auto-scanner's heuristic extractor was fed pages that don't list
# companies (country/city rankings, project portfolios, nav boilerplate),
# producing junk rows. These are quarantined: kept in a quarantine table
# for audit, excluded from the dashboard pipeline.
# ---------------------------------------------------------------------------
QUARANTINE_PATTERNS = [
    "WIPO Global Innovation Index",              # ranks countries, not companies
    "StartupBlink Global Startup Ecosystem Index",  # ranks cities/ecosystems
    "Startup Genome Global Startup Ecosystem Report",  # ranks ecosystems
    "Dealroom Global Tech Ecosystem Index",      # ranks ecosystems
    "BIS Innovation Hub Project Portfolio",     # project names, not companies
]

# Cookie-dialog / chrome junk that slipped into already-ingested rows
# (checked as whole-phrase, case-insensitive)
JUNK_NAMES = {
    "consent", "details", "necessary", "preferences", "performance",
    "marketing", "maximum storage duration", "type",
}

# Known cookie / localStorage / IndexedDB keys scraped as fake "companies"
# (audit 2026-10-06: they appear on MULTIPLE lists, which was inflating
# spotlight counts — e.g. YSC/OptanonConsent on 3-4 sources each)
COOKIE_JUNK = {
    "ysc", "visitor_info1_live", "optanonconsent", "jsessionid",
    "acastlang", "aplus_ls_key", "aplus_cna", "hmaccount", "hmaccount_bfess",
    "nrba_session_id", "analyticssynchistory", "logsdatabasev2",
    "ytidbmeta", "one_signal_sdk_db",
    # second wave found in audit (ad-tech / widget storage keys)
    "browserid", "ide", "nid", "googleadservingtest", "usermatchhistory",
    "uid", "richhistory", "widget",
}

# Generic nav-menu words scraped as fake "companies" (exact match only)
NAV_JUNK = {
    "events", "overview", "statistics", "features", "pricing", "blog",
    "careers", "press", "partners", "solutions", "products", "platform",
    "about us", "contact us", "use cases", "resources", "company",
    "insights", "newsroom", "leadership",
}

# Source label -> stable list_id (used for cross-list dedup + browse-by-list)
LIST_PATTERNS = [
    ("wef_tech_pioneers", ["WEF Technology Pioneers", "WEF Tech Pioneers"]),
    ("wef_global_innovators", ["WEF Global Innovators"]),
    ("wef_unicorns", ["WEF Unicorns"]),
    ("wef_uplink", ["UpLink"]),
    ("un_itu_wsis", ["WSIS Prizes", "ITU WSIS"]),
    ("worldbank_govtech", ["GovTech Innovation Challenge"]),
    ("endeavor_outliers", ["Endeavor Global Entrepreneurs", "Endeavor Outliers"]),
    ("endeavor_portfolio", ["Endeavor Entrepreneur Companies"]),
    ("slush_100", ["Slush 100"]),
    ("startup_world_cup", ["Startup World Cup"]),
    ("gitex_supernova", ["Supernova Challenge", "Expand North Star", "GITEX"]),
    ("nato_diana", ["NATO DIANA"]),
    ("g20_techsprint", ["G20 TechSprint"]),
    ("eu_innovation_radar", ["EU Innovation Radar"]),
    ("forbes_30u30", ["Forbes 30 Under 30", "Forbes 30U30"]),
    ("mit_tr35", ["MIT", "TR35", "35 Under 35", "Innovators Under 35"]),
    ("time100_next", ["TIME100 Next", "TIME 100 Next"]),
    ("fastco_mic", ["Most Innovative Companies", "Fast Company"]),
    ("cbinsights_ai100", ["CB Insights", "AI 100"]),
    ("xprize", ["XPRIZE", "Xprize"]),
    ("hello_tomorrow", ["Hello Tomorrow"]),
    ("eic_accelerator", ["EIC Accelerator", "EIC"]),
]

LIST_URLS = {
    "wef_tech_pioneers": "https://initiatives.weforum.org/technology-pioneers/home",
    "wef_global_innovators": "https://initiatives.weforum.org/innovator-communities/globalinnovators",
    "wef_unicorns": "https://initiatives.weforum.org/innovator-communities/organizations",
    "wef_uplink": "https://uplink.weforum.org/",
    "un_itu_wsis": "https://www.itu.int/hub/initiatives/wsis-prizes/",
    "worldbank_govtech": "https://www.worldbank.org/en/events/2025/11/26/govtech-innovation-challenge-award",
    "endeavor_outliers": "https://endeavor.org/2026-endeavor-outliers/",
    "endeavor_portfolio": "https://endeavor.org/entrepreneur-companies/",
    "slush_100": "https://www.slush.org",
    "startup_world_cup": "https://www.startupworldcup.io",
    "gitex_supernova": "https://www.expandnorthstar.com",
    "nato_diana": "https://www.diana.nato.int/",
    "g20_techsprint": "https://www.bis.org/about/bisih/topics/techsprint.htm",
    "eu_innovation_radar": "https://dealflow.eu/",
    "forbes_30u30": "https://www.forbes.com/30-under-30/",
    "mit_tr35": "https://www.technologyreview.com/innovators-under-35/",
    "time100_next": "https://time.com/collection/time100-next/",
    "fastco_mic": "https://www.fastcompany.com/most-innovative-companies/list",
    "cbinsights_ai100": "https://www.cbinsights.com/research/artificial-intelligence-top-startups/",
    "xprize": "https://www.xprize.org/prizes",
    "hello_tomorrow": "https://hello-tomorrow.org/the-challenge/",
    "eic_accelerator": "https://eic.ec.europa.eu/eic-funding-opportunities/eic-accelerator_en",
}

LIST_NAMES = {
    "wef_tech_pioneers": "WEF Technology Pioneers",
    "wef_global_innovators": "WEF Global Innovators",
    "wef_unicorns": "WEF Unicorns Community",
    "wef_uplink": "WEF UpLink Challenges",
    "un_itu_wsis": "UN ITU WSIS Prizes",
    "worldbank_govtech": "World Bank GovTech Awards",
    "endeavor_outliers": "Endeavor Outliers",
    "endeavor_portfolio": "Endeavor Entrepreneurs",
    "slush_100": "Slush 100",
    "startup_world_cup": "Startup World Cup",
    "gitex_supernova": "GITEX Supernova Challenge",
    "nato_diana": "NATO DIANA",
    "g20_techsprint": "G20 TechSprint",
    "eu_innovation_radar": "EU Innovation Radar Prize",
    "forbes_30u30": "Forbes 30 Under 30",
    "mit_tr35": "MIT Innovators Under 35",
    "time100_next": "TIME100 Next",
    "fastco_mic": "Fast Company Most Innovative",
    "cbinsights_ai100": "CB Insights AI 100",
    "xprize": "XPRIZE",
    "hello_tomorrow": "Hello Tomorrow",
    "eic_accelerator": "EU EIC Accelerator",
}

CORP_SUFFIX_RE = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|company|gmbh|"
    r"bv|sas|ab|plc|sa|pty|holdings?|group|labs?|technologies|tech|"
    r"systems|solutions|ventures|capital|partners)\b\.?$")

def norm_name(name):
    """Normalize a company name for cross-list dedup: lowercase, drop
    parentheticals, strip punctuation and corporate suffixes."""
    n = (name or "").strip().lower()
    n = re.sub(r"\s*\(.*?\)\s*", " ", n)
    n = re.sub(r"[^a-z0-9 ]", "", n)
    n = CORP_SUFFIX_RE.sub("", n).strip()
    n = re.sub(r"\s+", " ", n)
    return n

def is_quarantined(source):
    s = source or ""
    return any(p.lower() in s.lower() for p in QUARANTINE_PATTERNS)

def is_junk_name(name):
    t = (name or "").strip()
    tl = t.lower()
    if tl in JUNK_NAMES or tl in COOKIE_JUNK or tl in NAV_JUNK:
        return True
    # storage keys / HTML artifacts are never company names
    if "#" in t or " " in t or "_" in t or "::" in t:
        return True
    if re.search(r"\[x\d+\]", t):  # e.g. "CONSENT [x3]" cookie-count artifacts
        return True
    # event-agenda sentences scraped as entities
    if re.match(r"(?i)^(please note|session \d+\s*:)", t):
        return True
    return False

def derive_list_id(source):
    s = source or ""
    sl = s.lower()
    for lid, patterns in LIST_PATTERNS:
        if any(p.lower() in sl for p in patterns):
            return lid
    return None

def derive_cohort_year(source):
    """First 4-digit year in the source label, unless it's an auto-discovery
    stamp (that's the scan year, not the cohort year -> None)."""
    s = source or ""
    if "auto-discovered" in s.lower():
        return None
    m = re.search(r"\b(20\d\d|19\d\d)\b", s)
    return int(m.group(1)) if m else None

def load_outcomes():
    """Manual outcome curation: data/outcomes.csv keyed by normalized name.
    Columns: company,outcome,outcome_year,peak_valuation_usd,ticker,source_url,notes
    outcome in: unicorn | ipo | acquired | operating | defunct"""
    path = os.path.join(BASE, "data", "outcomes.csv")
    out = {}
    if not os.path.exists(path):
        return out
    import csv
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("company") or "").strip()
            if not name:
                continue
            out[norm_name(name)] = {
                "outcome": (row.get("outcome") or "").strip().lower(),
                "outcome_year": int(row["outcome_year"]) if (row.get("outcome_year") or "").strip().isdigit() else None,
                "peak_valuation_usd": float(row["peak_valuation_usd"]) if (row.get("peak_valuation_usd") or "").strip() else None,
                "ticker": (row.get("ticker") or "").strip() or None,
                "outcome_source": (row.get("source_url") or "").strip() or None,
                "outcome_notes": (row.get("notes") or "").strip() or None,
            }
    return out

def apply_historical_alumni(merged):
    """Inject verified historical list alumni (data/historical_alumni.csv).
    Upgrades existing rows (cohort year, verified flag, outcome) or adds
    new verified rows. This is how the 'which lists pick winners' leaderboard
    gets its denominator of known historical alumni."""
    path = os.path.join(BASE, "data", "historical_alumni.csv")
    if not os.path.exists(path):
        return merged
    import csv
    by_norm = {}
    for m in merged:
        by_norm.setdefault(norm_name(m["company"]), m)
    added = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("company") or "").strip()
            if not name:
                continue
            nm = norm_name(name)
            lid = (row.get("list_id") or "").strip() or None
            cy = row.get("cohort_year") or ""
            cy = int(cy) if cy.strip().isdigit() else None
            outcome = (row.get("outcome") or "").strip().lower() or None
            oy = row.get("outcome_year") or ""
            oy = int(oy) if oy.strip().isdigit() else None
            ticker = (row.get("ticker") or "").strip() or None
            src = (row.get("source_url") or "").strip() or None
            notes = (row.get("notes") or "").strip() or None
            existing = by_norm.get(nm)
            if existing:
                # upgrade: real cohort year + verified + outcome
                if cy and not existing.get("cohort_year"):
                    existing["cohort_year"] = cy
                existing["verified"] = 1
                if lid and lid not in (existing.get("list_ids") or []):
                    existing["list_ids"] = sorted(set((existing.get("list_ids") or []) + [lid]))
                    existing["spotlight_count"] = len(existing["list_ids"])
                    if not existing.get("source_url"):
                        existing["source_url"] = LIST_URLS.get(lid)
                if outcome and not existing.get("outcome"):
                    existing["outcome"] = outcome
                    existing["outcome_year"] = oy
                    existing["ticker"] = ticker
                    existing["outcome_source"] = src
                if notes:
                    existing["notes"] = (existing.get("notes") + " | " + notes) if existing.get("notes") else notes
            else:
                rec = {
                    "company": name, "primary_event": None, "thematic_probability": None,
                    "category": "Historical Alumni", "funding_stage": None, "ipo_date": None,
                    "sector": None, "source": f"{LIST_NAMES.get(lid, lid)} (historical alumni, verified)" if lid else "Historical alumni (verified)",
                    "notes": notes, "historical_flag": "Yes",
                    "stage_score": None, "financial_score": None, "capital_score": None,
                    "market_score": None, "risk_adj": None, "total_score": None, "grade": None,
                    "stage_rationale": None, "financial_rationale": None, "capital_rationale": None,
                    "market_rationale": None, "risk_rationale": None,
                    "list_id": lid, "cohort_year": cy,
                    "source_url": LIST_URLS.get(lid) if lid else None,
                    "spotlight_count": 1, "verified": 1,
                    "list_ids": [lid] if lid else [],
                    "all_sources": src or "",
                    "outcome": outcome, "outcome_year": oy, "ticker": ticker,
                    "outcome_source": src,
                }
                merged.append(rec)
                by_norm[nm] = rec
                added += 1
    if added:
        print(f"[ingest] historical alumni: upgraded {len([r for r in merged if r.get('historical_flag')=='Yes'])} rows, added {added} new")
    # re-sort: scored rows first, then historical
    merged.sort(key=lambda x: (x.get("total_score") if x.get("total_score") is not None else -999), reverse=True)
    return merged

def prob_num(p):
    if not p: return None
    m = re.match(r"(\d+(?:\.\d+)?)", str(p))
    return float(m.group(1)) if m else None

def build_pipeline(colored_rowsets, graded_rowsets):
    """Merge tracker views, then resolve entities ACROSS lists:
    the same company appearing on N independent lists is merged into one
    record with spotlight_count=N and a combined source list. Quarantined
    rows (junk sources / cookie-dialog names) go to a separate list.
    Returns (merged, quarantined)."""
    gl = {}
    for graded_rows in graded_rowsets:
        for r in (graded_rows or [])[1:]:
            if r and r[0]: gl[r[0].strip().lower()] = r

    raw, quarantined = [], []
    for colored_rows in colored_rowsets:
        for r in (colored_rows or [])[1:]:
            if not r or not r[2]: continue
            company = r[2]
            if is_junk_name(company):
                quarantined.append({"company": company, "reason": "junk name (chrome/consent boilerplate)", "source": r[7]})
                continue
            source = r[7] or ""
            if is_quarantined(source):
                quarantined.append({"company": company, "reason": "quarantined source (non-company list)", "source": source})
                continue
            key = company.strip().lower()
            g = gl.get(key)
            def gs(i): return g[i] if g and i < len(g) else None
            lid = derive_list_id(source)
            raw.append({
                "company": company, "norm": norm_name(company),
                "primary_event": r[0], "thematic_probability": r[1],
                "category": r[3], "funding_stage": r[4], "ipo_date": r[5],
                "sector": r[6] or gs(4), "source": source, "notes": r[8], "historical_flag": r[9],
                "stage_score": num(gs(6)), "financial_score": num(gs(7)), "capital_score": num(gs(8)),
                "market_score": num(gs(9)), "risk_adj": num(gs(10)), "total_score": num(gs(11)), "grade": gs(12),
                "stage_rationale": gs(13), "financial_rationale": gs(14), "capital_rationale": gs(15),
                "market_rationale": gs(16), "risk_rationale": gs(17),
                "list_id": lid, "cohort_year": derive_cohort_year(source),
                "source_url": LIST_URLS.get(lid) if lid else None,
                "verified": 0 if "auto-discovered" in source.lower() else 1,
            })

    # group by normalized name -> spotlight count
    groups = {}
    for rec in raw:
        groups.setdefault(rec["norm"] or rec["company"].strip().lower(), []).append(rec)

    outcomes = load_outcomes()
    merged = []
    for norm, recs in groups.items():
        # best record = highest total_score (human-graded research beats auto rows)
        recs.sort(key=lambda x: (x.get("total_score") if x.get("total_score") is not None else -999), reverse=True)
        best = dict(recs[0])
        oc = outcomes.get(norm)
        if oc:
            best["outcome"] = oc["outcome"]
            best["outcome_year"] = oc["outcome_year"]
            best["ticker"] = oc["ticker"]
            best["outcome_source"] = oc["outcome_source"]
        else:
            best["outcome"] = None; best["outcome_year"] = None
            best["ticker"] = None; best["outcome_source"] = None
        list_ids = [r["list_id"] for r in recs if r["list_id"]]
        sources = []
        for r in recs:
            if r["source"] and r["source"] not in sources:
                sources.append(r["source"])
        notes = " | ".join(dict.fromkeys(r["notes"] for r in recs if r["notes"]))
        best["spotlight_count"] = len(set(list_ids)) or 1
        best["list_ids"] = sorted(set(list_ids))
        best["all_sources"] = "; ".join(sources)
        if notes and notes != (best["notes"] or ""):
            best["notes"] = notes
        best["verified"] = max(r["verified"] for r in recs)
        # earliest cohort year seen
        years = [r["cohort_year"] for r in recs if r["cohort_year"]]
        best["cohort_year"] = min(years) if years else best["cohort_year"]
        del best["norm"]
        merged.append(best)

    merged.sort(key=lambda x: (x.get("total_score") if x.get("total_score") is not None else -999), reverse=True)
    return merged, quarantined

def main(folder=DEFAULT_FOLDER):
    os.makedirs(DATA, exist_ok=True)
    ts = now()
    files = sorted(glob.glob(os.path.join(folder, "*")))
    if not files:
        print(f"[ingest] No files found in {folder}"); return

    db = sqlite3.connect(DB_PATH)
    c = db.cursor()
    # schema migration: rebuild tables when the data-quality columns are missing
    cols_now = [r[1] for r in c.execute("PRAGMA table_info(pipeline)").fetchall()]
    if cols_now and ("list_id" not in cols_now or "outcome" not in cols_now or "first_seen" not in cols_now):
        print("[ingest] migrating pipeline schema (adding list/outcome columns)...")
        c.execute("DROP TABLE IF EXISTS pipeline")
        c.execute("DROP TABLE IF EXISTS quarantine")
    c.executescript("""
      CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, name TEXT, sha256 TEXT, size INT, ingested_at TEXT, sheets TEXT, row_count INT);
      CREATE TABLE IF NOT EXISTS pipeline (company TEXT, primary_event TEXT, thematic_probability TEXT, category TEXT, funding_stage TEXT,
        ipo_date TEXT, sector TEXT, source TEXT, notes TEXT, historical_flag TEXT, stage_score REAL, financial_score REAL, capital_score REAL,
        market_score REAL, risk_adj REAL, total_score REAL, grade TEXT, stage_rationale TEXT, financial_rationale TEXT, capital_rationale TEXT,
        market_rationale TEXT, risk_rationale TEXT, list_id TEXT, cohort_year INT, source_url TEXT,
        spotlight_count INT DEFAULT 1, verified INT DEFAULT 0, all_sources TEXT,
        outcome TEXT, outcome_year INT, ticker TEXT, outcome_source TEXT,
        first_seen TEXT, ingested_at TEXT);
      CREATE TABLE IF NOT EXISTS quarantine (company TEXT, reason TEXT, source TEXT, ingested_at TEXT);
      CREATE TABLE IF NOT EXISTS methodology (file TEXT, line TEXT);
    """)
    existing = {r[0] for r in c.execute("SELECT sha256 FROM files")}
    lineage, payloads, new_count = [], {}, 0

    for f in files:
        if os.path.isdir(f): continue
        name = os.path.basename(f)
        h = sha(f)
        is_new = h not in existing
        if is_new:
            new_count += 1
            print(f"[ingest] INGEST (new): {name}  (sha {h[:16]})")
            c.execute("INSERT INTO files(name,sha256,size,ingested_at) VALUES(?,?,?,?)", (name, h, os.path.getsize(f), ts))
            existing.add(h); ing_ts = ts
        else:
            print(f"[ingest] already ingested (re-parsing for rebuild): {name}")
            ing_ts = (c.execute("SELECT ingested_at FROM files WHERE sha256=?", (h,)).fetchone() or [ts])[0]
        lineage.append({"name": name, "sha256": h[:16], "size": os.path.getsize(f), "ingested_at": ing_ts})
        if name.lower().endswith(".xlsx"): payloads[name] = load_xlsx(f)
        elif name.lower().endswith(".pdf"): payloads[name] = load_pdf(f)

    def find_xlsx(pred):
        for n, d in payloads.items():
            if n.lower().endswith(".xlsx") and pred(d): return d
        return None

    def find_all_xlsx(pred):
        return [d for n, d in payloads.items() if n.lower().endswith(".xlsx") and pred(d)]

    col_all = find_all_xlsx(lambda d: any("Master Pipeline Tracker" in s for s in d))
    grd_all = find_all_xlsx(lambda d: any("Graded Pipeline" in s for s in d))
    orgs = find_xlsx(lambda d: any("Master Overview" in s for s in d))
    icf = find_xlsx(lambda d: any("Comprehensive Report" in s for s in d))
    pdf = next((d for n, d in payloads.items() if n.lower().endswith(".pdf")), None)

    c.execute("DELETE FROM pipeline"); c.execute("DELETE FROM methodology"); c.execute("DELETE FROM quarantine")
    colored_rowsets = [d.get("Master Pipeline Tracker") for d in col_all]
    colored_sum = next((d.get("Summary & Methodology") for d in col_all if d.get("Summary & Methodology")), None)
    graded_rowsets = [d.get("Graded Pipeline") for d in grd_all]
    graded_meth = next((d.get("Methodology") for d in grd_all if d.get("Methodology")), None)
    orgs_master = orgs.get("Master Overview") if orgs else None
    orgs_readme = orgs.get("README") if orgs else None

    merged, quarantined = build_pipeline(colored_rowsets, graded_rowsets) if colored_rowsets else ([], [])
    merged = apply_historical_alumni(merged)
    # first-seen tracking (survives rebuilds) for NEW badges
    db.execute("CREATE TABLE IF NOT EXISTS first_seen (norm TEXT PRIMARY KEY, first_seen TEXT)")
    table_was_empty = db.execute("SELECT COUNT(*) FROM first_seen").fetchone()[0] == 0
    for m in merged:
        nm = norm_name(m["company"])
        row = db.execute("SELECT first_seen FROM first_seen WHERE norm=?", (nm,)).fetchone()
        if row:
            m["first_seen"] = row[0]
        else:
            # On the very first run, everything already in the DB is
            # established (not new) — backdate so only future discoveries
            # get NEW badges.
            m["first_seen"] = "2020-01-01T00:00:00+00:00" if table_was_empty else ts
            db.execute("INSERT OR IGNORE INTO first_seen(norm, first_seen) VALUES(?,?)", (nm, m["first_seen"]))
        m["ingested_at"] = ts
        row = dict(m); row.pop("list_ids", None)
        cols = [k for k in row.keys()]
        c.execute("INSERT INTO pipeline (" + ",".join(cols) + ",ingested_at) VALUES (" + ",".join(["?"] * len(cols)) + ",?)",
                  [row[k] for k in cols] + [ts])
    for q in quarantined:
        c.execute("INSERT INTO quarantine(company,reason,source,ingested_at) VALUES(?,?,?,?)",
                  (q["company"], q["reason"], q["source"], ts))
    if graded_meth:
        for ln in graded_meth:
            if ln and ln[0]: c.execute("INSERT INTO methodology(file,line) VALUES(?,?)", ("GRADED", ln[0]))
    db.commit()

    meth_lines = [m[0] for m in graded_meth if m and m[0]] if graded_meth else []
    first_colored = next((r for r in colored_rowsets if r), [[]])
    first_graded = next((r for r in graded_rowsets if r), [[]])
    headers = {"colored": first_colored[0] if first_colored else [], "graded": first_graded[0] if first_graded else []}
    # lists metadata for browse-by-list + spotlight counts
    # + outcome hit-rate per list ("which lists pick winners")
    list_counts = {}
    list_wins = {}
    for m in merged:
        for lid in (m.get("list_ids") or []):
            list_counts[lid] = list_counts.get(lid, 0) + 1
            if (m.get("outcome") or "") in ("unicorn", "ipo", "acquired"):
                list_wins[lid] = list_wins.get(lid, 0) + 1
    lists_meta = [
        {"id": lid, "name": LIST_NAMES.get(lid, lid), "url": LIST_URLS.get(lid),
         "count": cnt, "wins": list_wins.get(lid, 0),
         "hit_rate": round(list_wins.get(lid, 0) / cnt, 3) if cnt else 0}
        for lid, cnt in sorted(list_counts.items(), key=lambda x: -x[1])
    ]
    # seasoned alumni analysis + news feed for the IPO'd section
    seasoned = []
    seasoned_path = os.path.join(BASE, "results", "seasoned.csv")
    if os.path.exists(seasoned_path):
        import csv as _csv
        with open(seasoned_path, newline="", encoding="utf-8") as f:
            seasoned = list(_csv.DictReader(f))
    news_bundle = {}
    news_path = os.path.join(BASE, "data", "news", "news.json")
    if os.path.exists(news_path):
        with open(news_path, encoding="utf-8") as f:
            news_bundle = json.load(f)
    playbook = {}
    playbook_path = os.path.join(BASE, "results", "playbook.json")
    if os.path.exists(playbook_path):
        with open(playbook_path, encoding="utf-8") as f:
            playbook = json.load(f)
    payload = {
        "generated_at": ts, "headers": headers, "companies": merged, "count": len(merged),
        "lists": lists_meta,
        "seasoned": seasoned,
        "news": news_bundle,
        "playbook": playbook,
        "quarantined_count": len(quarantined),
        "quarantined_sample": [{"company": q["company"], "reason": q["reason"]} for q in quarantined[:25]],
        "methodology": meth_lines, "colored_summary": colored_sum or [],
        "orgs_overview": orgs_master or [], "orgs_readme": [r[0] for r in orgs_readme if r and r[0]] if orgs_readme else [],
        "ic_sheets": list(icf.keys()) if icf else [], "ic_comprehensive": icf.get("Comprehensive Report", []) if icf else [],
        "ic_analysis": icf.get("Analysis (Cross-Tally)", []) if icf else [],
        "pdf_pages": pdf["pages"] if pdf else 0, "pdf_text": pdf["text"] if pdf else "",
        "lineage": lineage,
    }
    os.makedirs(os.path.dirname(SITE_DATA), exist_ok=True)
    with open(SITE_DATA, "w") as fh:
        fh.write("window.PIPELINE_DATA = " + json.dumps(payload, default=str) + ";")

    print(f"\n[ingest] DONE. New files: {new_count} | Entities: {len(merged)} | Sources: {len(lineage)}")
    print(f"[ingest] Database: {DB_PATH}")
    print(f"[ingest] Dashboard data: {SITE_DATA}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FOLDER)
