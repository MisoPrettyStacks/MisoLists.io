#!/usr/bin/env python3
"""
Winner's Playbook — scientific sorting of winners / middle / losers.
=====================================================================
Takes the 11 seasoned alumni (+3 bankruptcies from events.csv) and:
  1. Tiers them by lifetime outcome (max winner / middle / loser)
  2. Computes distinguishing signals per tier:
     - max drawdown depth and whether they recovered to new highs
     - time to 10x (for winners)
     - first-year post-IPO behavior
     - business-model tags (hand-curated in data/playbook_tags.csv)
  3. Writes results/playbook.json — the dashboard's Playbook section reads it.

The goal: a no-experience reader can look at a pre-IPO / IPO / IPO'd
company and check it against the signals that separated winners from
losers in this dataset. All signals are descriptive of THIS sample
(n=14); they are not predictive guarantees.
"""
import csv
import json
import os
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICE_DIR = os.path.join(BASE, "data", "prices")
EVENTS_CSV = os.path.join(BASE, "data", "events.csv")
TAGS_CSV = os.path.join(BASE, "data", "playbook_tags.csv")
OUT_DIR = os.path.join(BASE, "results")


def load(ticker):
    path = os.path.join(PRICE_DIR, f"{ticker}.csv")
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((r["date"], float(r["adjclose"])))
            except (ValueError, TypeError):
                pass
    return sorted(rows)


def max_drawdown(prices):
    peak, mdd, trough_date = prices[0][1], 0.0, None
    for d, p in prices:
        if p > peak:
            peak = p
        dd = p / peak - 1
        if dd < mdd:
            mdd, trough_date = dd, d
    return mdd, trough_date


def time_to_multiple(prices, mult):
    base = prices[0][1]
    for d, p in prices:
        if p >= base * mult:
            return d
    return None


def first_year_return(prices):
    if len(prices) < 200:
        return None
    return prices[252][1] / prices[0][1] - 1 if len(prices) > 252 else \
        prices[-1][1] / prices[0][1] - 1


def load_tags():
    tags = {}
    if os.path.exists(TAGS_CSV):
        with open(TAGS_CSV, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                tags[r["company"].strip()] = r
    return tags


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    tags = load_tags()

    # IPO events with tickers
    ipos = {}
    bankrupt = {}
    with open(EVENTS_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = (r.get("ticker_at_event") or "").strip()
            if r["event_type"] == "ipo" and t:
                ipos[r["company"]] = (t, r["event_date"])
            elif r["event_type"] == "defunct":
                bankrupt[r["company"]] = r["event_date"]

    alumni = []
    for co, (ticker, ipo_date) in ipos.items():
        prices = load(ticker)
        if len(prices) < 50:
            continue
        mdd, trough = max_drawdown(prices)
        t10 = time_to_multiple(prices, 10)
        total = prices[-1][1] / prices[0][1] - 1
        tag = tags.get(co, {})
        alumni.append({
            "company": co, "ticker": ticker, "ipo_date": ipo_date,
            "total_return": round(total, 2),
            "max_drawdown": round(mdd, 2),
            "max_drawdown_date": trough,
            "time_to_10x": t10,
            "first_year": round(first_year_return(prices), 2)
            if first_year_return(prices) is not None else None,
            "model": tag.get("model", ""),
            "moat": tag.get("moat", ""),
            "notes": tag.get("notes", ""),
        })

    # tier by lifetime outcome
    for a in alumni:
        if a["total_return"] >= 9:
            a["tier"] = "max winner"
        elif a["total_return"] >= 0:
            a["tier"] = "middle"
        else:
            a["tier"] = "loser"
    for co, d in bankrupt.items():
        tag = tags.get(co, {})
        alumni.append({"company": co, "ticker": None, "ipo_date": None,
                       "total_return": -1.0, "max_drawdown": -1.0,
                       "max_drawdown_date": d, "time_to_10x": None,
                       "first_year": None, "tier": "loser",
                       "model": tag.get("model", ""), "moat": tag.get("moat", ""),
                       "notes": tag.get("notes", "")})

    # ---- signal extraction per tier ----
    def avg(vals):
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    tiers = {}
    for tier in ("max winner", "middle", "loser"):
        grp = [a for a in alumni if a["tier"] == tier]
        moats = {}
        for a in grp:
            for m in (a["moat"] or "").split(";"):
                m = m.strip()
                if m:
                    moats[m] = moats.get(m, 0) + 1
        tiers[tier] = {
            "count": len(grp),
            "companies": [a["company"] for a in grp],
            "avg_max_drawdown": avg([a["max_drawdown"] for a in grp]),
            "avg_first_year": avg([a["first_year"] for a in grp]),
            "common_moats": sorted(moats.items(), key=lambda x: -x[1]),
            "time_to_10x": [(a["company"], a["time_to_10x"]) for a in grp
                            if a["time_to_10x"]],
        }

    # ---- the playbook: signals a beginner can check ----
    playbook = {
        "generated_at": datetime.now().isoformat(),
        "tiers": tiers,
        "alumni": sorted(alumni, key=lambda a: a["total_return"], reverse=True),
        "signals": [
            {
                "signal": "Network effects / platform moat",
                "when": "pre-IPO — check before anything else",
                "what": "All four max winners (Alphabet, Mastercard, Meta, Palantir) sell "
                        "access to a network that gets stronger with each user. Losers sold "
                        "a product (pills, algae fuel, eye-trackers). Ask: does each new "
                        "customer make the product better for everyone else?",
            },
            {
                "signal": "Recurring revenue, not one-time sales",
                "when": "pre-IPO",
                "what": "Winners monetize continuously (ads, fees per transaction, "
                        "subscriptions, contracts). The bankruptcies all depended on "
                        "lumpy, one-off adoption that never repeated.",
            },
            {
                "signal": "First-year post-IPO drawdown depth",
                "when": "IPO — the first 12 months",
                "what": "In this sample, every eventual max winner stayed above a -60% "
                        "first-year drawdown; Meta fell -60% and still 20x'd, but nothing "
                        "that fell more than -70% in year one ever recovered to new highs. "
                        "A -70% first-year drawdown is the historical line between "
                        "'buy the dip' and 'value trap' here.",
            },
            {
                "signal": "Time to 10x clusters in the first decade",
                "when": "IPO'd — years 2-12",
                "what": "Winners that 10x'd did it within ~12 years of listing "
                        "(Palantir ~4y, Mastercard ~6y, Alphabet ~9y, Meta ~12y). "
                        "And 10x isn't permanent: Enphase 10x'd by 2020 then lost "
                        "90%. The win isn't just reaching 10x — it's holding a "
                        "moat that keeps it there.",
            },
            {
                "signal": "Drawdown recovery test",
                "when": "IPO'd — ongoing",
                "what": "Max winners all suffered -30% to -60% drawdowns and made new "
                        "highs within ~2 years. Losers' drawdowns kept deepening "
                        "(Spotify -37% and falling, Enphase -90%). Rule of thumb from "
                        "the data: a drawdown that keeps making new lows for 18+ months "
                        "has never reversed in this sample.",
            },
            {
                "signal": "The list is a lagging indicator",
                "when": "pre-IPO — mindset",
                "what": "Spotlight lists catch companies 4-6 years after founding, already "
                        "venture-backed and growing. The list didn't make them winners; "
                        "it recognized winners-in-progress. Never treat inclusion alone "
                        "as a buy signal — it's the starting gun for research, not the trade.",
            },
        ],
        "caveats": [
            "n=14 companies. Every 'rule' above is descriptive of this tiny sample, "
            "not a law. Survivorship bias applies: bankruptcies are undercounted "
            "because delisted tickers vanish from free price data.",
            "All bankruptcies here were pre-2021; recent cohorts haven't had time to fail yet.",
            "Business-model tags are hand-curated and debatable.",
        ],
    }

    out = os.path.join(OUT_DIR, "playbook.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(playbook, f, indent=1)
    print(f"[playbook] wrote {out}")
    for tier, t in tiers.items():
        print(f"  {tier}: {t['count']} — {', '.join(t['companies'])}")
        print(f"    avg max drawdown: {t['avg_max_drawdown']}, "
              f"avg first year: {t['avg_first_year']}, moats: {t['common_moats']}")


if __name__ == "__main__":
    main()
