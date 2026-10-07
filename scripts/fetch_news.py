#!/usr/bin/env python3
"""
News feed — Google News RSS (free, no key).
==========================================
Fetches ~6 recent headlines per seasoned-alumni company plus 4 per
industry, caches to data/news/*.json. The dashboard's Seasoned Alumni
section reads the cache — no live fetching from the browser.

Run weekly (or on demand):
  python3 scripts/fetch_news.py
"""
import csv
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS_DIR = os.path.join(BASE, "data", "news")
TICKERS_CSV = os.path.join(BASE, "data", "tickers.csv")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# company -> industry search terms for the "industry impacts" feed
INDUSTRY_QUERIES = {
    "Alphabet": "big tech AI regulation",
    "Mastercard": "payments fintech regulation",
    "Palantir": "AI defense tech government contracts",
    "Meta": "social media AI regulation",
    "Spotify": "music streaming industry",
    "Wise": "fintech cross-border payments",
    "Enphase Energy": "solar energy industry",
    "Airbnb": "short-term rental regulation travel",
    "Dropbox": "cloud storage SaaS",
    "LanzaTech": "sustainable aviation fuel carbon capture",
    "Tobii AB": "eye tracking AR VR",
}


def fetch_rss(query, n=6):
    q = urllib.parse.quote(query)
    url = (f"https://news.google.com/rss/search?q={q}"
           f"&hl=en-US&gl=US&ceid=US:en")
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            root = ET.fromstring(r.read())
    except Exception as e:
        print(f"    RSS failed for {query!r}: {e}")
        return []
    items = []
    import itertools
    for it in itertools.islice(root.iter("item"), n):
        title = it.findtext("title") or ""
        link = it.findtext("link") or ""
        pub = it.findtext("pubDate") or ""
        src = ""
        source_el = it.find("source")
        if source_el is not None:
            src = source_el.text or ""
        # clean up Google's "Title - Source" duplication
        title = re.sub(r"\s*-\s*[^-]+$", "", html.unescape(title)).strip()
        items.append({"title": html.unescape(title), "link": link,
                      "published": pub, "source": src})
    return items


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main():
    os.makedirs(NEWS_DIR, exist_ok=True)
    companies = []
    with open(TICKERS_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["ticker"].strip() == "^GSPC":
                continue
            companies.append(r["company"].strip())

    bundle = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "companies": {}}
    for co in companies:
        print(f"  {co} ...", end=" ", flush=True)
        news = fetch_rss(f"{co} stock", n=6)
        industry_q = INDUSTRY_QUERIES.get(co)
        industry = fetch_rss(industry_q, n=4) if industry_q else []
        bundle["companies"][slug(co)] = {
            "company": co,
            "news": news,
            "industry": industry,
            "industry_query": industry_q,
        }
        print(f"{len(news)} headlines, {len(industry)} industry")
        time.sleep(1.5)

    path = os.path.join(NEWS_DIR, "news.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=1)
    print(f"[news] wrote {path}")


if __name__ == "__main__":
    main()
