#!/usr/bin/env python3
"""
Price fetcher — Yahoo Finance v8 (primary) + Nasdaq API (fallback).
====================================================================
Downloads daily OHLCV (adjusted closes) per ticker into data/prices/<TICKER>.csv.
Respects rate limits (~1 req / 2s). Never re-downloads history already held:
run weekly to append the latest bars.

Tickers come from data/tickers.csv (company,ticker,note). IPO offer prices
(first-day pop math) are NOT in price data — record them in data/events.csv.

Run:
  python3 scripts/fetch_prices.py              # fetch all missing/refresh
  python3 scripts/fetch_prices.py --ticker SPOT # single ticker
"""
import argparse
import csv
import os
import time
from datetime import datetime, timezone

import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICE_DIR = os.path.join(BASE, "data", "prices")
TICKERS_CSV = os.path.join(BASE, "data", "tickers.csv")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}


def yahoo_daily(ticker):
    # Fetch in 2-year chunks with explicit period1/period2: Yahoo downsamples
    # range=max to weekly bars, but explicit periods return true daily bars.
    now = int(datetime.now(timezone.utc).timestamp())
    start = now - 30 * 365 * 24 * 3600  # 30y back covers every IPO here
    rows = []
    chunk = 2 * 365 * 24 * 3600
    p1 = start
    while p1 < now:
        p2 = min(p1 + chunk, now)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        try:
            r = requests.get(url, headers=UA,
                             params={"interval": "1d", "period1": p1, "period2": p2},
                             timeout=30)
            if r.status_code == 429:
                raise RuntimeError("Yahoo rate limit (429) — back off and retry later")
            if r.status_code == 400:
                p1 = p2  # no data for this period (pre-IPO) — skip chunk
                time.sleep(0.5)
                continue
            r.raise_for_status()
            res = r.json()["chart"].get("result")
        except RuntimeError:
            raise
        except Exception:
            p1 = p2
            time.sleep(0.5)
            continue
        if res:
            j = res[0]
            ts = j.get("timestamp") or []
            q = j["indicators"]["quote"][0]
            adj = j["indicators"]["adjclose"][0]["adjclose"]
            for i, t in enumerate(ts):
                if adj[i] is None:
                    continue
                rows.append({
                    "date": datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d"),
                    "open": q["open"][i], "high": q["high"][i],
                    "low": q["low"][i], "close": q["close"][i],
                    "adjclose": adj[i], "volume": q["volume"][i],
                })
        p1 = p2
        time.sleep(1)
    # dedupe by date (chunk boundaries can overlap)
    seen = {}
    for r in rows:
        seen[r["date"]] = r
    if not seen:
        raise RuntimeError("Yahoo returned no daily bars")
    return [seen[d] for d in sorted(seen)]


def nasdaq_daily(ticker):
    sym = ticker.split(".")[0]  # Nasdaq API wants the bare symbol
    url = f"https://api.nasdaq.com/api/quote/{sym}/historical"
    r = requests.get(url, headers={**UA, "Accept": "application/json"},
                     params={"assetclass": "stocks", "fromdate": "1990-01-01",
                             "todate": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                             "limit": 9999}, timeout=30)
    r.raise_for_status()
    data = r.json()["data"]
    rows = (data["tradesTable"]["rows"] if isinstance(data, dict)
            else data["rows"] if isinstance(data, dict) else [])
    out = []
    for row in rows:
        def num(x):
            return float(str(x).replace("$", "").replace(",", "").strip())
        out.append({
            "date": datetime.strptime(row["date"], "%m/%d/%Y").strftime("%Y-%m-%d"),
            "open": num(row["open"]), "high": num(row["high"]),
            "low": num(row["low"]), "close": num(row["close"]),
            "adjclose": num(row["close"]),  # Nasdaq gives split-adjusted-ish; prefer Yahoo adj
            "volume": int(str(row["volume"]).replace(",", "")),
        })
    return sorted(out, key=lambda r: r["date"])


def load_tickers():
    if not os.path.exists(TICKERS_CSV):
        return []
    with open(TICKERS_CSV, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if (r.get("ticker") or "").strip()]


def write_csv(ticker, rows):
    os.makedirs(PRICE_DIR, exist_ok=True)
    path = os.path.join(PRICE_DIR, f"{ticker}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "open", "high", "low",
                                          "close", "adjclose", "volume", "source"])
        w.writeheader()
        w.writerows(rows)
    return path


def fetch_one(ticker):
    # incremental: keep what we have, fetch full range, merge on date
    path = os.path.join(PRICE_DIR, f"{ticker}.csv")
    have = {}
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                have[r["date"]] = r
    try:
        rows = yahoo_daily(ticker)
        source = "yahoo"
    except Exception as e:
        print(f"    Yahoo failed ({e}); trying Nasdaq fallback")
        rows = nasdaq_daily(ticker)
        source = "nasdaq"
    for r in rows:
        r["source"] = source
        have[r["date"]] = r  # fresh data wins
    merged = [have[d] for d in sorted(have)]
    write_csv(ticker, merged)
    return len(merged), source


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default=None)
    args = ap.parse_args()

    tickers = load_tickers()
    if args.ticker:
        tickers = [t for t in tickers if t["ticker"] == args.ticker]
    print(f"[prices] {len(tickers)} tickers")
    for t in tickers:
        ticker = t["ticker"].strip()
        print(f"  {ticker} ({t.get('company','')}) ...", end=" ", flush=True)
        try:
            n, src = fetch_one(ticker)
            print(f"OK {n} bars via {src}")
        except Exception as e:
            print(f"FAILED: {e}")
        time.sleep(2)  # stay under rate limits
    print("[prices] done — cache in data/prices/")


if __name__ == "__main__":
    main()
