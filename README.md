# ⚠️ Personal Research Experiment Financial Disclaimer & Liability Waiver
Not a Tool or Service: This is a private, experimental sandbox. It is not a financial tool, software service, or product designed for public use.
Not Financial Advice: The author is not a licensed financial advisor, accountant, or broker. Nothing in this repository constitutes professional financial, investment, or legal advice.
No Warranties: This repository is provided "as-is" for display purposes only. The author makes no representations or warranties of any kind regarding the accuracy, completeness, or reliability of the data, code, or experimental models.
Absolute Limitation of Liability: Under no circumstances shall the author be liable for any claims, damages, or financial losses (direct or indirect) if you violate these terms and attempt to use, replicate, or rely on any part of this experiment.

## MisoLists.io Strategic Pipeline — Executive Control Room

A free, autonomous, agentic -research pipeline. Drop new reports,
agendas, or forecasts into [`reports/`](./reports) and the system collects,
normalizes, scores, and publishes them to a live executive dashboard.

**Live dashboard:** https://misoprettystacks.github.io/MisoLists.io/

## How it works

1. **Ingestion** — `ingest.py` SHA-256 dedupes every file in `reports/`,
   parses Excel + PDF, normalizes and merges the two tracker views by company,
   and rebuilds the SQLite database (`data.db`) with full source lineage.
2. **Dashboard data** — regenerates `assets/data.js`, the data bundle the
   static dashboard reads.
3. **Publishing** — GitHub Actions commits the regenerated data and rebuilds
   GitHub Pages. The live site updates automatically.

## Autonomous triggers

`.github/workflows/ingest.yml` runs ingestion:
- on every push that changes `reports/**` (new report lands → instant update),
- daily on a schedule (re-ingest cadence),
- on manual dispatch.

Everything runs on GitHub's free tier — no server, no credits, no maintenance.

## Agentic source scanning

`.github/workflows/pioneer-sources.yml` runs `scripts/pioneer_sources.py`
weekly (plus on manual dispatch, plus whenever the script itself changes).
It scans a registry of international tech-pioneer / innovator recognition
programs (WEF's 4 lists, UN/IGO programs, global startup-ecosystem indices,
Endeavor, and pitch competitions), fetches each source with a headless
browser (handles JS-rendered pages and most bot-detection walls), extracts
named entities, and writes `reports/Pioneer_Innovator_Sources_AUTO.xlsx` in
the same Master Pipeline Tracker / Graded Pipeline schema as everything
else. That commit lands in `reports/` and automatically triggers
`ingest.yml`, which merges it into the live dashboard — no manual
spreadsheet work required.

New entities are scored conservatively: an award/cohort selection alone
(Stage 5, Financial 0, Capital 0, Market 0, Risk −5 → Grade F) — the same
convention already used for NATO DIANA / G20 TechSprint cohort-only rows.
Grade F on an auto-discovered row means "insufficient public disclosure to
grade," not "bad company"; re-score it by hand once real financial/investor
data becomes public.

Sources the scanner can't reliably parse (blocked, or a press-release page
rather than an actual roster) are logged as `NEEDS_REVIEW` in the workbook's
"Scrape Log" sheet rather than silently skipped or faked. Verified manual
research can be dropped into `scripts/seed_data/<source_id>.json` (a plain
list of entity names) as a fallback for sources that are hard to scrape
live — see `wef_tech_pioneers.json` for an example.

## The two tracker views

- **Master Pipeline Tracker** (Colored workbook, sheet 2) — thematic view of 76
  entities, color-coded by geopolitical / IGO-NGO forecast theme.
- **Graded Pipeline** (Graded workbook, sheet 1) — the same 76 entities scored
  across Stage, Financial Traction, Capital Backing, Market Position, and Risk.
- **Methodology** (Graded workbook, sheet 2) — the grading formula and rules.

The dashboard joins these into one unified, filterable control room.

## Add a new report

1. Drop the `.xlsx` or `.pdf` file into `reports/`.
2. Commit and push to `main`.
3. GitHub Actions ingests it and republishes the dashboard — usually within ~1 minute.

## Run locally

```bash
pip install -r requirements.txt
python3 ingest.py          # ingests reports/ and regenerates assets/data.js
```

Then open `index.html` in a browser, or serve with `python3 -m http.server`.

## Notes

This system supports research and learning. It does **not** provide
personalized investment advice or profit guarantees. The grading methodology
explicitly treats thematic correlation as context, not evidence of returns.
