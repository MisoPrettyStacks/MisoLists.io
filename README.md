# Strategic Investment Pipeline — Executive Control Room

A free, autonomous, agentic investment-research pipeline. Drop new reports,
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

This system supports research and decision-making. It does **not** provide
personalized investment advice or profit guarantees. The grading methodology
explicitly treats thematic correlation as context, not evidence of returns.
