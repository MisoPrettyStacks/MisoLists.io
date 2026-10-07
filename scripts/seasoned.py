#!/usr/bin/env python3
"""
Seasoned alumni — where are the long-public spotlight alumni NOW?
==================================================================
For every IPO event in data/events.csv with price data, computes:
  - years public
  - total return since first-day close (vs S&P 500 buy-and-hold)
  - current drawdown from all-time high
  - 1-year momentum (trailing 252 trading days)
  - state: a plain-English read of the current setup

This answers "these IPO'd years ago — what do they look like now, and
which ones are cooking?" Writes results/seasoned.csv and prints a table.

Not investment advice. Backward-looking only.
"""
import csv
import math
import os
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICE_DIR = os.path.join(BASE, "data", "prices")
EVENTS_CSV = os.path.join(BASE, "data", "events.csv")
OUT_DIR = os.path.join(BASE, "results")
MARKET = "^GSPC"


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


def pct(a, b):
    return (b / a - 1) if a else None


def analyze(company, ticker, ipo_date, prices, mkt):
    s = dict(prices)
    m = dict(mkt)
    dates = sorted(d for d in s if d in m)
    if not dates:
        return None
    first = next((d for d in dates if d >= ipo_date), None)
    if not first:
        return None
    last = dates[-1]
    years = (datetime.strptime(last, "%Y-%m-%d") -
             datetime.strptime(first, "%Y-%m-%d")).days / 365.25

    total = pct(s[first], s[last])
    total_mkt = pct(m[first], m[last])
    excess = (total - total_mkt) if total is not None and total_mkt is not None else None

    ath = max(s[d] for d in dates)
    ath_date = max(d for d in dates if s[d] == ath)
    dd = pct(ath, s[last])

    y1 = (datetime.strptime(last, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")
    d1 = next((d for d in dates if d >= y1), None)
    mom1y = pct(s[d1], s[last]) if d1 else None

    # 52-week range position + volatility for the outlook read
    yr_dates = [d for d in dates if d >= y1] if y1 else []
    hi52 = max(s[d] for d in yr_dates) if yr_dates else None
    lo52 = min(s[d] for d in yr_dates) if yr_dates else None
    range_pos = ((s[last] - lo52) / (hi52 - lo52) if hi52 and lo52 and hi52 != lo52
                 else None)
    # annualized volatility from daily log returns (last year)
    rets = []
    prev = None
    for d in yr_dates:
        if prev is not None:
            rets.append(math.log(s[d] / s[prev]))
        prev = d
    vol = (sum((r - sum(rets) / len(rets)) ** 2 for r in rets) / len(rets)) ** 0.5 * math.sqrt(252) \
        if len(rets) > 20 else None

    # ---- 12-month setup read (mechanical, not a prediction) ----
    # bull/base/bear framed from trend + range position + drawdown
    if range_pos is not None and range_pos > 0.8 and (mom1y or 0) > 0:
        outlook, outlook_why = ("constructive",
            "Trading in the top fifth of its 52-week range with positive momentum — "
            "the trend is up until the range breaks.")
    elif dd is not None and dd > -0.15:
        outlook, outlook_why = ("constructive",
            "Within 15% of all-time highs — long-term uptrend intact; "
            "shallow pullbacks have been the buying pattern.")
    elif (mom1y or 0) > 0.25:
        outlook, outlook_why = ("repairing",
            "Strong year (+25%+) but still well off highs — recovery in progress, "
            "watch whether momentum survives the next pullback.")
    elif dd is not None and dd < -0.5:
        outlook, outlook_why = ("distressed",
            "Down more than half from highs — the market has repriced the story; "
            "needs a fundamental catalyst, not just a bounce.")
    elif (mom1y or 0) < -0.2:
        outlook, outlook_why = ("deteriorating",
            "Down 20%+ on the year — downtrend dominant; "
            "no sign of a turn until momentum stabilizes.")
    else:
        outlook, outlook_why = ("mixed",
            "No clean trend — chopping. Range position and news flow "
            "matter more than direction here.")

    # plain-English state
    if dd is not None and dd > -0.10 and (mom1y or 0) > 0:
        state = "cooking — near highs and rising"
    elif dd is not None and dd > -0.10:
        state = "at highs but stalling"
    elif dd is not None and dd > -0.30 and (mom1y or 0) > 0.15:
        state = "recovering — bouncing off lows"
    elif dd is not None and dd <= -0.30 and (mom1y or 0) > 0:
        state = "beaten down but turning"
    elif dd is not None and dd <= -0.30:
        state = "deep drawdown, still falling"
    elif (mom1y or 0) > 0.20:
        state = "strong momentum"
    else:
        state = "drifting"

    return {
        "company": company, "ticker": ticker,
        "ipo_date": ipo_date, "years_public": round(years, 1),
        "return_since_ipo": round(total, 3) if total is not None else None,
        "sp500_since_ipo": round(total_mkt, 3) if total_mkt is not None else None,
        "excess_vs_sp500": round(excess, 3) if excess is not None else None,
        "drawdown_from_ath": round(dd, 3) if dd is not None else None,
        "ath_date": ath_date,
        "momentum_1y": round(mom1y, 3) if mom1y is not None else None,
        "range_position_52w": round(range_pos, 2) if range_pos is not None else None,
        "volatility_ann": round(vol, 3) if vol is not None else None,
        "last_price_date": last,
        "state": state,
        "outlook": outlook,
        "outlook_why": outlook_why,
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    mkt = load(MARKET)
    ipos = []
    with open(EVENTS_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["event_type"] == "ipo" and (r.get("ticker_at_event") or "").strip():
                ipos.append(r)

    results = []
    for ev in ipos:
        ticker = ev["ticker_at_event"].strip()
        prices = load(ticker)
        if not prices:
            print(f"  skip {ev['company']}: no price file")
            continue
        out = analyze(ev["company"], ticker, ev["event_date"], prices, mkt)
        if out:
            results.append(out)

    results.sort(key=lambda r: (r["excess_vs_sp500"]
                                 if r["excess_vs_sp500"] is not None else -999),
                 reverse=True)

    print(f"\n{'Company':<14} {'IPO':<12} {'Yrs':>4} {'Since IPO':>10} {'vs S&P':>9} "
          f"{'Drawdn':>8} {'1y mom':>8}  State")
    print("-" * 105)
    for r in results:
        si = f"{r['return_since_ipo']:+.0%}" if r["return_since_ipo"] is not None else "n/a"
        ex = f"{r['excess_vs_sp500']:+.0%}" if r["excess_vs_sp500"] is not None else "n/a"
        dd = f"{r['drawdown_from_ath']:.0%}" if r["drawdown_from_ath"] is not None else "n/a"
        mo = f"{r['momentum_1y']:+.0%}" if r["momentum_1y"] is not None else "n/a"
        print(f"{r['company']:<14} {r['ipo_date']:<12} {r['years_public']:>4.0f} "
              f"{si:>10} {ex:>9} {dd:>8} {mo:>8}  {r['state']}")

    out = os.path.join(OUT_DIR, "seasoned.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    print(f"\n[seasoned] wrote {out} ({len(results)} alumni)")


if __name__ == "__main__":
    main()
