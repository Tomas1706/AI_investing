# AI Investing — One‑Shot Research Report Generator

Produce a conservative, evidence‑based research report for a single US stock in one run, using SEC filings as the primary source of truth. The pipeline fetches recent filings, extracts structured XBRL facts, computes auditable value‑oriented metrics, applies simple rule‑based signals, and writes a plain‑text/Markdown report. Optional integrations add insider activity and an LLM‑written memo.

Core goals:
- SEC‑first facts with explicit provenance (no invented numbers)
- Deterministic metrics and simple thresholds (no normalization)
- Clear verdict: Investigate Further / Watch / Avoid‑for‑now


## Features
- SEC submissions fetch: latest 10‑K, last 2–3 10‑Q, 8‑K (≤90d), DEF 14A, Form 4 (24m)
- XBRL extraction: revenue, COGS, gross profit, EBIT proxy, net income, diluted shares, CFO, CapEx, cash, debt, current ratio inputs, interest expense, D&A
- Metrics: revenue CAGR window, margin level/stability, interest coverage, liquidity, net debt/EBITDA, FCF consistency, share count trend
- Insider activity (optional via Alpha Vantage): 3/6/12m net buys, clustered buying, routine selling
- Signals and classification with confidence level
- Markdown report with sources and file paths for auditability
- Optional LLM memo via OpenAI API


## Requirements
- Python 3.11+
- Recommended: a virtual environment
- Internet access to SEC and optional Alpha Vantage/OpenAI endpoints

Python dependencies are declared in `pyproject.toml` and installed via pip or uv.


## Quickstart
1) Create and activate a virtual environment
   - macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`
   - Windows (PowerShell): `python -m venv .venv; .\.venv\Scripts\Activate.ps1`

2) Install the project (installs dependencies)
   - Pip: `pip install -e .`
   - Or using uv: `uv sync` (if you use uv; `uv.lock` is included)

3) Create a `.env` file in the repo root (example below)

4) Run the pipeline (examples in the Usage section)


## Configuration (.env)
The app reads configuration from environment variables and an optional `.env` file. Example template:

```
# Required for SEC requests — follow SEC fair‑use guidance
SEC_USER_AGENT="your-org/ai-investing your-email@example.com"

# Where outputs and caches are written (will be created if missing)
OUTPUT_DIR=reports

# Optional: if provided, the pipeline can run without ticker→CIK resolution
# Use a 10‑digit CIK (zero‑padded). Example (Apple): 0000320193
OVERRIDE_CIK=

# Optional integrations
# Alpha Vantage (fundamentals + insider transactions)
ALPHAVANTAGE_API_KEY=

# OpenAI (memo generation)
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

Notes:
- `SEC_USER_AGENT` should be descriptive per SEC rules: `<org>/<app> <contact-email>`.
- If `OUTPUT_DIR` is not writable, the app falls back to `./reports`.


## Usage
The main entry point is the module `ai_investing.run`. Ticker→CIK resolution is not yet implemented, so for a full end‑to‑end run you should pass both `--ticker` (for output path naming) and `--cik` (to fetch SEC data).

Quick test command (copy/paste):

```
python3 -m ai_investing.run --ticker AAPL --cik 0000320193 --out report
```

Basic help:

```
python3 -m ai_investing.run --help
```

End‑to‑end SEC‑only run (Apple example):

```
python3 -m ai_investing.run \
  --ticker AAPL \
  --cik 0000320193 \
  --out reports \
  --asof 2024-12-31
```

Include Alpha Vantage fundamentals and insiders (requires `ALPHAVANTAGE_API_KEY`):

```
python3 -m ai_investing.run \
  --ticker AAPL \
  --cik 0000320193 \
  --alpha-vantage
```

Add an LLM memo (requires `OPENAI_API_KEY`):

```
python3 -m ai_investing.run --ticker AAPL --cik 0000320193 --alpha-vantage --llm
```

Flags summary:
- `--ticker` US ticker symbol (used for naming outputs)
- `--cik` 10‑digit CIK to fetch SEC data; bypasses ticker lookup
- `--out` output directory root (defaults to `OUTPUT_DIR` or `./reports`)
- `--asof` date filter `YYYY-MM-DD` (limits filings considered)
- `--alpha-vantage` include Alpha Vantage series/insiders
- `--llm` generate LLM memo if `OPENAI_API_KEY` is set
- `--verbose` increase verbosity


## Outputs
Artifacts are written under `OUTPUT_DIR` (default `reports/`):
- Final report: `reports/<TICKER>/<TICKER>_YYYY-MM-DD.md`
- SEC cache: `reports/.cache/sec/<CIK10>/`
  - `submissions.json`, `filings_metadata.json`, `companyfacts.json`, `timeseries.(parquet|json)`
  - Derived: `metrics.json`, `signals.json`, `classification.json`
- Alpha Vantage cache (optional): `reports/.cache/web/alpha_vantage/<TICKER>/`
  - `timeseries.json`, `metrics.json`, `insider_transactions.json`, `insiders_summary.json`


## How It Works (Pipeline)
1) SEC filings retrieval via submissions API (polite backoff)
2) XBRL facts extraction and tidy timeseries assembly
3) Deterministic metrics (CAGR, margins, FCF, leverage, coverage, liquidity)
4) Insider analysis (optional Alpha Vantage): windows, cluster/routine heuristics
5) Rule‑based signals and red‑flag overrides; classification + confidence
6) Markdown report with citations and file paths; optional LLM memo

See `docs/mvp_implementation_plan.md` and `docs/plan.md` for the full design and roadmap.


## Troubleshooting
- SEC 429/Rate‑limit: Ensure `SEC_USER_AGENT` is set correctly; reruns include backoff.
- Missing Parquet: If `pyarrow`/`pandas` are unavailable, timeseries falls back to JSON.
- Alpha Vantage errors: Set `ALPHAVANTAGE_API_KEY`; the pipeline continues if unavailable.
- OpenAI memo missing: Set `OPENAI_API_KEY` and `--llm`; failures are non‑fatal.
- Windows path issues: The code falls back to shorter cache paths if needed.


## Repo Layout
- `run.py` CLI orchestrator
- `config.py` env/.env loader, app config
- `sec.py` SEC client, filings fetch, XBRL extraction
- `metrics.py` deterministic metric computations with provenance
- `analysis.py` rule‑based signals and red flags
- `scoring.py` classification and confidence
- `insiders.py` insider activity analysis (Alpha Vantage)
- `web.py` optional web/Alpha Vantage helpers
- `report.py` Markdown report writer
- `docs/` design plans and MVP checklist


## Limitations and Roadmap
- Ticker→CIK resolution is not implemented yet; pass `--cik` or set `OVERRIDE_CIK`.
- Valuation is not included in the MVP; future work may add FCF yield, conservative DCF, and peer comps.
- Public web context (beyond Alpha Vantage) and Bright Data MCP integration are future phases.


## Fair‑Use Note (SEC)
Please provide a descriptive `SEC_USER_AGENT` and respect SEC rate‑limit guidance. This tool uses polite retries and limited concurrency.
