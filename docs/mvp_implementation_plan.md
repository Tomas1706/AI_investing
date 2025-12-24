# MVP Implementation Plan (Pipeline-First, SEC-Only)

Use this checklist to drive implementation. Each step includes success criteria that must be met before moving forward.

## Tracking Legend
- [ ] = Pending
- [x] = Done

## 1) Config + Project Scaffolding
- [x] Implement `config.py` that loads from `.env` and environment variables.
  - Success criteria:
    - `SEC_USER_AGENT` and `OUTPUT_DIR` are read correctly.
    - Missing vars produce clear warnings with safe defaults.
    - `.env` is ignored by git (`.gitignore` contains `.env`).
- [x] Create basic module skeletons: `run.py`, `sec.py`, `metrics.py`, `insiders.py`, `report.py`, `cache.py` (optional), `analysis.py`, `scoring.py`.
  - Success criteria:
    - Each module imports without errors and exposes stubbed functions.
    - `run.py --help` prints CLI usage.

## 2) Ticker → CIK Resolution (US Only)
- [ ] Implement `sec.resolve_ticker(ticker)` with cache.
  - Success criteria:
    - Resolves US tickers to `{cik, company_name}` using SEC `company_tickers.json` (or successor).
    - Non‑US/invalid tickers produce a clear error and exit code ≠ 0.
    - Local cache (JSON or Parquet) prevents repeated network calls.
- [ ] Add overrides/disambiguation for dual‑listed/ADR cases.
  - Success criteria:
    - `--cik` CLI option bypasses ticker lookup.
    - If multiple matches are found (rare), CLI prints choices and exits with guidance.

## 3) SEC Filings Retrieval
- [x] Implement retrieval for 10‑K, last 2–3 10‑Q, recent 8‑K (≤90 days), DEF 14A, and Form 4 (24‑month lookback).
  - Success criteria:
    - Files metadata captured: form type, filing date, accession, SEC URL.
    - Raw text stored (or pointer/URL if text fetch is deferred) with consistent paths.
    - Respect SEC rate limits: custom `User‑Agent`, 429 backoff, bounded concurrency.
    - Partial unavailability does not crash; logs warnings and proceeds.

## 4) Structured Data Extraction (XBRL)
- [ ] Implement XBRL extraction with tag priority map and fallbacks.
  - Success criteria:
    - Extracts time series for revenue, COGS, gross profit, operating income, net income, diluted shares, CFO, CapEx, cash, debt components, current assets/liabilities, interest expense, D&A.
    - Applies tag priority and fallbacks; logs which tag provided each metric.
    - Produces tidy time series (by fiscal period) stored in Parquet when appropriate.
    - Handles missing tags gracefully and marks metrics “Not available”.

## 5) Deterministic Metrics (No LLM)
- [ ] Compute key value metrics using GAAP and derived formulas.
  - Success criteria:
    - Revenue CAGR computed over the longest available window (prefer 10y; else 7y; else 5y) and window explicitly reported.
    - Gross/operating margin levels and stability computed (std‑dev; flag >5pp single‑year drops).
    - FCF = CFO − CapEx, interest coverage = EBIT/Interest; EBITDA = EBIT + D&A (labeled approximation).
    - Liquidity and leverage: current ratio, net debt, net debt/EBITDA (or FCF fallback when EBITDA not meaningful).
    - Each metric records provenance (filing, date, accession, URL).

## 6) Insider Activity (Form 4)
- [ ] Parse Form 4 to compute net buys/sells over 3, 6, 12 months; clustered/routine heuristics.
  - Success criteria:
    - Aggregations are correct across reporting owners and transaction codes (exclude derivatives unless clearly comparable).
    - Clustered buying signal triggers when ≥3 insiders buy within 30 days with ≥0.1% diluted shares or ≥$500k aggregate.
    - Routine selling is detected (regular cadence ±20% size); routine sales are down‑weighted.
    - Output includes a clear owner‑alignment assessment.

## 7) Rule‑Based Signals, Red Flags, and Classification
- [ ] Build explicit signals and red‑flag overrides (no normalization).
  - Success criteria:
    - Signals cover durability, margins, balance sheet, capital allocation, and insider alignment.
    - Red‑flags (any triggers Avoid‑for‑now): sustained negative FCF (≥2y), net debt/EBITDA > 4x or interest coverage < 2x, material weaknesses/restatements/going‑concern, repeated >15% revenue declines without recovery.
    - Overall classification outputs one of: Investigate Further / Watch / Avoid‑for‑now.
    - Confidence level computed from data coverage and signal consistency (High/Medium/Low).

## 8) Report Generation (Text Only)
- [ ] Generate `reports/<TICKER>/<TICKER>_YYYY-MM-DD.txt` with sections and citations.
  - Success criteria:
    - Sections: Business overview, Durability/Moat, Financial strength, Capital allocation/management, Insider activity, Key risks/failure modes, Long‑term verdict and confidence, What would change my mind, Sources/citations.
    - All metrics and statements include provenance or “Not available”.
    - Script exits 0 on success; non‑fatal data gaps still produce a file but return a non‑zero code if configured.

## 9) CLI Orchestration and Pipeline Persistence
- [ ] Orchestrate steps in `run.py` with persisted intermediates.
  - Success criteria:
    - Each step callable independently for testing.
    - Intermediate artifacts (JSON/Parquet) saved with stable paths and content hashes.
    - `--asof` restricts periods considered by the pipeline; price/FX not used in MVP.

## 10) Minimal QA Pass
- [ ] Run the pipeline for 2–3 large‑cap tickers (e.g., AAPL, MSFT) and one edge case (thin filer) to validate robustness.
  - Success criteria:
    - Reports produced with expected structure.
    - Logs show tag selection, missing data handling, and rate‑limit compliance.
    - Manual spot checks confirm citations map to correct filings.
