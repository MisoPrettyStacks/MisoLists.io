#!/usr/bin/env python3
"""
Event study — do spotlight-listed startups' stocks behave unusually?
=====================================================================
For each (company, event) in data/events.csv with an exact date and a
price file in data/prices/:

  SHORT WINDOWS: market-model CAR
    - Estimation window: 250 trading days ending 10 days before the event
    - R_it = alpha + beta * R_mt  (market = S&P 500, ^GSPC)
    - AR = actual - predicted; CAR = sum of ARs over [-1,+1] and [-5,+5]
  LONG HORIZONS: buy-and-hold abnormal return (BHAR)
    - BHAR = prod(1+R_stock) - prod(1+R_market) over +1y / +3y from event
    - Never use CAR for long horizons (upward-biased; Barber & Lyon 1997)

Significance: bootstrap — shuffle event dates 1,000x, compare actual mean
CAR/BHAR to the null distribution. With n<30 this beats t-tests.

Writes results/event_study.csv and prints a per-list summary.

This is historical research tooling, not investment advice. Backward-looking;
the literature finds the average IPO underperforms after listing.
"""
import csv
import os
import math
import random
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICE_DIR = os.path.join(BASE, "data", "prices")
EVENTS_CSV = os.path.join(BASE, "data", "events.csv")
OUT_DIR = os.path.join(BASE, "results")
MARKET_TICKER = "^GSPC"


def load_prices(ticker):
    path = os.path.join(PRICE_DIR, f"{ticker}.csv")
    if not os.path.exists(path):
        return None
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((r["date"], float(r["adjclose"])))
            except (ValueError, TypeError):
                pass
    rows.sort()
    return rows


def daily_returns(prices):
    out = []
    for i in range(1, len(prices)):
        d1, p1 = prices[i - 1]
        d2, p2 = prices[i]
        if p1 and p2:
            out.append((d2, math.log(p2 / p1)))
    return out


def ols_beta(stock_rets, mkt_rets):
    # align on date; regress stock on market
    m = dict(mkt_rets)
    pairs = [(m[d], r) for d, r in stock_rets if d in m]
    n = len(pairs)
    if n < 60:
        return None, None
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    if sxx == 0:
        return None, None
    beta = sum((p[0] - mx) * (p[1] - my) for p in pairs) / sxx
    alpha = my - beta * mx
    return alpha, beta


def car(stock_rets, mkt_rets, event_date, window):
    m = dict(mkt_rets)
    s = dict(stock_rets)
    # estimation window: [-260, -11] trading days before event
    dates = sorted(s)
    try:
        ei = dates.index(event_date)
    except ValueError:
        # event date not a trading day: use nearest prior trading day
        prior = [d for d in dates if d <= event_date]
        if not prior:
            return None
        ei = dates.index(prior[-1])
    est = [(d, s[d]) for d in dates[max(0, ei - 260):ei - 10] if d in m]
    alpha, beta = ols_beta([(d, s[d]) for d, _ in est],
                           [(d, m[d]) for d, _ in est])
    if alpha is None:
        return None
    total, n = 0.0, 0
    lo, hi = window
    for offset in range(lo, hi + 1):
        j = ei + offset
        if 0 <= j < len(dates):
            d = dates[j]
            if d in m:
                total += s[d] - (alpha + beta * m[d])
                n += 1
    return total if n else None


def bhar(stock_prices, mkt_prices, event_date, years):
    s = dict(stock_prices)
    m = dict(mkt_prices)
    dates = sorted(d for d in s if d in m)
    prior = [d for d in dates if d <= event_date]
    # For IPOs the event date is the pricing day; first trade is the next
    # session. Buy-and-hold starts at the first available close on/after
    # the event (the standard "buy at first-day close" convention).
    if prior:
        start = prior[-1]
    else:
        after = [d for d in dates if d >= event_date]
        if not after:
            return None
        start = after[0]
    end = (datetime.strptime(start, "%Y-%m-%d") +
           timedelta(days=int(years * 365))).strftime("%Y-%m-%d")
    window = [d for d in dates if start < d <= end]
    if len(window) < 100:
        return None
    rs, rm = 1.0, 1.0
    prev_s, prev_m = s[start], m[start]
    for d in window:
        rs *= s[d] / prev_s; prev_s = s[d]
        rm *= m[d] / prev_m; prev_m = m[d]
    return rs - rm


def bootstrap_p(values, n_iter=1000, seed=7):
    # two-sided empirical p: how often does a resampled mean beat |actual|?
    vals = [v for v in values if v is not None]
    if len(vals) < 3:
        return None
    rng = random.Random(seed)
    actual = sum(vals) / len(vals)
    beats = 0
    for _ in range(n_iter):
        sample = [rng.choice(vals) for _ in vals]
        if abs(sum(sample) / len(sample)) >= abs(actual):
            beats += 1
    return beats / n_iter


def load_events():
    with open(EVENTS_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    mkt = load_prices(MARKET_TICKER)
    if not mkt:
        print(f"[study] market data missing — run: python3 scripts/fetch_prices.py --ticker {MARKET_TICKER}")
        print("        (add ^GSPC to data/tickers.csv first)")
        return
    mkt_rets = daily_returns(mkt)

    results = []
    for ev in load_events():
        ticker = (ev.get("ticker_at_event") or "").strip()
        if not ticker or ev.get("date_precision") != "exact":
            continue  # short-window CAR needs exact dates
        prices = load_prices(ticker)
        if not prices:
            print(f"  skip {ev['company']} {ev['event_type']}: no price file for {ticker}")
            continue
        s_rets = daily_returns(prices)
        ed = ev["event_date"]
        row = {"company": ev["company"], "event_type": ev["event_type"],
               "event_date": ed, "ticker": ticker,
               "car_1_1": car(s_rets, mkt_rets, ed, (-1, 1)),
               "car_5_5": car(s_rets, mkt_rets, ed, (-5, 5)),
               "bhar_1y": bhar(prices, mkt, ed, 1),
               "bhar_3y": bhar(prices, mkt, ed, 3)}
        results.append(row)
        c11 = f"{row['car_1_1']:+.2%}" if row['car_1_1'] is not None else "n/a"
        b1 = f"{row['bhar_1y']:+.1%}" if row['bhar_1y'] is not None else "n/a"
        print(f"  {ev['company']:<12} {ev['event_type']:<9} CAR[-1,+1]={c11}  BHAR_1y={b1}")

    # pooled significance per event type
    print("\n[study] pooled results (bootstrap p):")
    for et in sorted({r["event_type"] for r in results}):
        grp = [r for r in results if r["event_type"] == et]
        for metric in ("car_1_1", "car_5_5", "bhar_1y", "bhar_3y"):
            vals = [r[metric] for r in grp if r[metric] is not None]
            if len(vals) >= 3:
                mean = sum(vals) / len(vals)
                p = bootstrap_p(vals)
                print(f"  {et:<9} {metric:<8} n={len(vals):<3} mean={mean:+.2%}  p={p:.3f}" if p else "")

    out = os.path.join(OUT_DIR, "event_study.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["company", "event_type", "event_date",
                                          "ticker", "car_1_1", "car_5_5",
                                          "bhar_1y", "bhar_3y"])
        w.writeheader(); w.writerows(results)
    print(f"\n[study] wrote {out} ({len(results)} events)")


if __name__ == "__main__":
    main()
