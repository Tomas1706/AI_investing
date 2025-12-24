# One‑Shot Value Investing Research Script — Full Implementation Plan

## Purpose
Build a Python script that runs on demand for a single US stock ticker and produces a long‑term, value‑investing research report as a text file.

The script answers this question:

“Is this a durable business worth owning for many years at a reasonable price, based on conservative, evidence‑based analysis?”

The script is not periodic; it runs once when invoked.

## 1. User Interaction and Execution
The script is executed from the command line.

Example command:

```
python run.py --ticker AAPL
```

Optional arguments:
- `--out <directory>` (default: `reports/`)
- `--asof <YYYY-MM-DD>` (default: today)
- `--no-web` (skip Bright Data MCP and web sources)

The script always produces an output file unless the ticker is invalid or non‑US.

Output file path:

```
reports/AAPL/AAPL_YYYY-MM-DD.txt
```

Rules:
- Create `--out` directory tree automatically; if creation fails, fall back to `./reports` and log a warning.
- `--asof` filters filings and computed metrics by filing periods up to the date; price/FX data is not used in MVP.

## 2. Core Rules the Script Must Obey
- SEC data is the primary source of truth.
- Public web data is secondary and used only in later phases.
- No numbers may be invented.
- Every numeric metric must have a source.
- If data is missing, say “Not available”.
- Facts are extracted first; narrative is written last.
- The tone must be conservative and long‑term.
- The result is not “buy/sell”, but one of:
  - Investigate Further
  - Watch
  - Avoid‑for‑now
Sources focus: SEC only for MVP (10‑K, 10‑Q, 8‑K, DEF 14A, Form 4). Non‑SEC used later and never override SEC facts.

## 3. High‑Level Execution Flow
When `run.py` executes, it performs these steps in order:
- Resolve ticker → CIK.
- Download relevant SEC filings.
- Extract structured financial data from SEC.
- Compute value‑oriented financial metrics.
- Analyze insider activity (Form 4).
- Assemble a complete SEC evidence bundle.
- Optionally retrieve web context via Bright Data MCP (later phase).
- Validate and filter web data (later phase).
- Construct rule‑based signals and flags (no normalization).
- Compute a conservative long‑term score using thresholds and overrides.
- Ask an LLM to write a value‑investing memo.
- Write the final report to a text file.

Each step must be callable and testable independently.
Pipeline: Steps are implemented as a pipeline with persisted intermediates for reproducibility.

## 4. Files and Modules Codex Should Create
At minimum, the codebase should contain:
- `run.py`
- `config.py`
- `sec.py`
- `metrics.py`
- `insiders.py`
- `web.py`
- `web_validate.py`
- `analysis.py`
- `scoring.py`
- `llm.py`
- `report.py`
- `cache.py` (optional but recommended)

Codex may split these further, but responsibilities should remain equivalent.
Caching/backend: Use filesystem cache; prefer Parquet for structured time‑series where applicable. `config.py` loads from a `.env` file (kept in `.gitignore`) and environment variables.

## 5. Step 1 — Ticker Resolution (US Only)
Input:
- Ticker string (e.g., “AAPL”).

Action:
- Look up the ticker in SEC data.
- Resolve it to a CIK and official company name.

Rules:
- If the ticker does not exist or is not US‑listed, exit with a clear error.
- Cache the ticker → CIK mapping locally.

Output:
- `cik`
- `company_name`
Notes:
- Use SEC `company_tickers.json` (or successor) as the authoritative ticker→CIK source.
- Dual‑listed/ADR handling: keep an alternative selection mechanism (e.g., `--cik` override or interactive disambiguation) [open decision: exact UX TBD].

## 6. Step 2 — SEC Filings Retrieval
For the resolved CIK, retrieve:
- Latest 10‑K
- Last 2–3 10‑Q filings
- Any 8‑K filings from the last 90 days
- All Form 4 filings from the last 24 months (default; configurable)
- Latest DEF 14A (proxy statement), if available

For each filing, store:
- Form type
- Filing date
- Accession number
- SEC URL
- Raw filing text

If a filing type is unavailable, continue with others.
Implementation notes:
- Respect SEC fair‑use guidance: add a descriptive `User‑Agent`, apply backoff on 429, and rate‑limit requests.

## 7. Step 3 — Structured SEC Financial Data Extraction
From SEC XBRL or structured endpoints, extract:
- Income statement history
- Balance sheet history
- Cash flow statement history
- Diluted shares outstanding history
- Segment revenue (if disclosed)

Normalize all data into numeric time series indexed by fiscal period.
See “XBRL Tag Priority Map” below for prioritized tags and fallbacks. Use GAAP XBRL facts for core logic; derived metrics must be GAAP‑based and clearly labeled.

## 8. Step 4 — Deterministic Metric Computation (No LLM)
Using only Python logic, compute long‑term value metrics.

Business durability:
- Revenue CAGR (multi‑year)
- Revenue drawdowns in weak years
- Segment concentration flags
- Customer concentration flags (from filings)

Economic moat proxies:
- Gross margin level
- Gross margin stability over time
- Operating margin trend
- ROIC or ROE persistence

Financial strength:
- Net debt / EBITDA (or net debt / FCF fallback)
- Interest coverage ratio
- Current ratio
- Free cash flow consistency

Capital allocation:

Free cash flow usage breakdown:
- reinvestment (capex)
- buybacks
- dividends
- debt reduction
- acquisitions
- Share count trend (dilution vs reduction)
- Stock‑based compensation as % of revenue (if available)

Each metric must include provenance:
- Source filing
- Filing date
- Accession number
- SEC URL
Defaults:
- CAGR windows: prefer 10‑year; fallback to 7‑year, then 5‑year if shorter history. Report window length used.
- EBITDA (derived): `OperatingIncomeLoss + DepreciationDepletionAndAmortization`. Label as GAAP‑derived approximation.
- FCF: `NetCashProvidedByUsedInOperatingActivities − PaymentsToAcquirePropertyPlantAndEquipment` (with fallbacks).
- Interest coverage: `OperatingIncomeLoss / InterestExpense` (report “Not meaningful/Not available” if negative/missing).
- Stability thresholds: gross margin std‑dev ≤2pp very stable; 2–4pp stable; >4pp unstable; flag >5pp single‑year drop.
- Concentration detection: use explicit disclosures; otherwise detect qualitative phrases in filings and flag without inventing percentages.

## 9. Step 5 — Insider Activity Analysis (Form 4)
Parse Form 4 filings to compute:
- Net shares bought or sold over 3, 6, and 12 months
- Number of unique insiders buying vs selling
- Detection of clustered activity
- Executive weighting (CEO, CFO, Chair matter more)
- Simple routine‑selling heuristic

Produce a summarized insider behavior assessment focused on owner alignment.
Heuristics:
- Clustered buying: ≥3 insiders execute open‑market buys within 30 days totaling ≥0.1% of diluted shares or ≥$500k aggregate.
- Clustered selling: ≥3 insiders sell within 30 days; down‑weight if 10b5‑1 plan indicated.
- Routine selling heuristic: repeated small sales by the same insider on a regular cadence (e.g., monthly/quarterly lots within ±20% size) flagged as routine; exclude from negative signals unless size accelerates ≥2x.

## 10. Step 6 — SEC Evidence Bundle
Combine all SEC‑derived information into a single structured object:
- Company identity
- Financial metrics
- Insider summary
- Extracted factual claims from filings
- Citations and evidence snippets

This object is immutable and becomes the primary factual input for later steps.
Persistence: persist bundle to disk (JSON/Parquet) with a content hash for reproducibility and memo regeneration.

## 11. Step 7 — Public Web Supplement (Optional)
If web is enabled, retrieve additional context using Bright Data MCP.

Web data should be used ONLY to support long‑term value questions:
- Competitive landscape and market structure
- Market share commentary (if reputable)
- Long‑term regulatory or legal risks
- Durable demand drivers
- Current stock price / market cap (if not using an API)

Rules:
- Limit total scraped pages (default max: 8)
- Prefer reputable sources (company IR, regulators, major finance outlets)
- Avoid hype, price targets, or social sentiment
Notes: Bright Data MCP accessed via API (later phase). Authentication via env‑loaded creds.

## 12. Step 8 — Web Data Extraction and Validation
Extract web claims using a strict schema. For every claim, store:
- Claim text
- Source URL
- Supporting quote/snippet
- Confidence level

Validation rules:
- Numeric claims require strong sources
- Prefer multiple sources for numbers
- Downweight web signals vs SEC signals
- Discard low‑quality or speculative sources
Confidence scale (for web, later phase): High / Medium / Low.
- High: official regulators, company IR filings with direct quotes; multiple independent confirmations.
- Medium: major finance outlets or industry reports with clear sourcing.
- Low: blogs, forums, unverified claims; discard if numeric.

## 13. Step 9 — Rule‑Based Signals and Flags (No Normalization)
Construct explicit, auditable signals and flags using thresholds; do not normalize to 0–1.

Each signal includes:
- Name
- Raw value and units
- Threshold evaluation (pass/fail/flag)
- Evidence references (filing, date, accession, URL)

Emphasize:
- Durability (multi‑year revenue/FCF growth with limited drawdowns)
- Moat persistence (gross/operating margin stability)
- Balance sheet protection (net debt, liquidity)
- Capital allocation discipline (FCF usage, dilution)
- Insider alignment (net buying, clustered buys)

## 14. Step 10 — Long‑Term Value Scoring and Classification
Compute category scores using conservative weights:
- Business durability
- Moat and ROIC persistence
- Financial strength
- Capital allocation quality
- Valuation (later phase)
- Insider alignment

Apply red‑flag overrides (any triggers “Avoid‑for‑now”):
- Sustained negative FCF (≥2 consecutive fiscal years) without clear improvement.
- Net debt/EBITDA > 4.0x or interest coverage < 2.0x.
- Material weaknesses in ICFR, restatements, going‑concern warnings.
- Repeated large revenue declines (>15%) without recovery.

Final classification:
- Investigate Further
- Watch
- Avoid‑for‑now

Confidence level (data‑driven):
- High: ≥80% metric coverage with consistent signals (durability, margins, balance sheet) and no major missing filings.
- Medium: 50–79% coverage or mixed signals without red flags.
- Low: <50% coverage, conflicting signals, or partial data.

## 15. Step 11 — LLM Synthesis (Memo Writing Only)
Pass the following to the LLM:
- SEC evidence bundle
- Validated web claims
- Computed metrics and scores

Final classification.

The LLM must:
- Write a sober, long‑term value‑investing memo
- Explain reasoning clearly
- Highlight uncertainty and risks
- Avoid introducing new numbers
- Explicitly state what could break the thesis
Later phase detail: specify model, token budget, and style guide when enabling this step.

## 16. Step 12 — Report Generation
Generate a plain text report with these sections:
- Business overview
- Business durability and moat
- Financial strength
- Capital allocation and management behavior
- Insider activity
- Valuation and margin of safety
- Key risks and failure modes
- Long‑term verdict and confidence
- What would change my mind
- Sources and citations

Write the file to disk at `reports/<TICKER>/<TICKER>_YYYY-MM-DD.txt`.

Optional: also emit a JSON facts/metrics file for programmatic use (later phase).

## 17. Error Handling and Guarantees
- If the ticker is invalid or non‑US: exit early with a clear message.
- If some data fails to load: continue and note missing sections.
- Always produce an output file if the ticker is valid.
- Never silently ignore missing data.
Exit codes: partial failures still produce a report and return non‑zero exit code while logging missing sections.

## 18. MVP vs Later

MVP (SEC‑only; immediately useful for decisions):
- Ticker → CIK resolution (with `--cik` override for disambiguation).
- SEC filings retrieval (10‑K, 10‑Q, recent 8‑K, DEF 14A; Form 4 with 24‑month lookback).
- Structured data extraction from SEC XBRL per tag priority map.
- Deterministic metric computation (CAGR, margins, FCF, leverage, coverage, liquidity).
- Insider activity analysis with cluster/routine heuristics.
- Rule‑based signals and red‑flag overrides; conservative classification (Investigate Further / Watch / Avoid‑for‑now).
- Report generation to `reports/<TICKER>/<TICKER>_YYYY-MM-DD.txt` with sources/citations.

Later extensions:
- Add valuation using market price data (e.g., FCF yield, conservative DCF, peer multiples).
- Public web supplement via Bright Data MCP with validation and confidence scoring.
- LLM memo synthesis using the SEC evidence bundle.
- Programmatic JSON outputs and richer cache/index (Parquet datasets).

Open decisions:
- Dual‑listed/ADR selection UX (flag/interactive vs `--cik` only).

---

## XBRL Tag Priority Map (US Issuers)

Notes:
- Tag variability is real. Implement: (1) short priority list, (2) close aliases, (3) fall back to statement line‑item extraction if needed.
- Use GAAP XBRL facts for core scoring; derived metrics must be GAAP‑based and labeled. Non‑GAAP is supplemental only and never overrides GAAP.

1) Income Statement Metrics
- Revenue (priority): `us-gaap:Revenues`, `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`
  - Common fallbacks: `us-gaap:SalesRevenueNet`, `us-gaap:SalesRevenueGoodsNet`, `us-gaap:SalesRevenueServicesNet`
  - Financials model fallback (banks/insurers): `us-gaap:InterestAndDividendIncomeOperating`, `us-gaap:InvestmentIncomeInterestAndDividend`
- Cost of revenue/COGS (priority): `us-gaap:CostOfRevenue`
  - Fallbacks: `us-gaap:CostOfGoodsAndServicesSold`, `us-gaap:CostOfGoodsSold`, `us-gaap:CostOfServices`
- Gross profit (priority): `us-gaap:GrossProfit`; fallback compute = revenue − cost_of_revenue
- Operating income (EBIT proxy) (priority): `us-gaap:OperatingIncomeLoss`
  - Fallback: `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxes` (less ideal)
- Net income (priority): `us-gaap:NetIncomeLoss`
  - Fallbacks: `us-gaap:ProfitLoss`, `us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic`
- Shares (dilution trend): `us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding`, `us-gaap:WeightedAverageNumberOfSharesOutstandingDiluted`
  - Fallback: `us-gaap:CommonStockSharesOutstanding` (point‑in‑time)

2) Cash Flow Metrics (FCF)
- CFO (priority): `us-gaap:NetCashProvidedByUsedInOperatingActivities`
  - Fallback: `us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations`
- Capex (priority): `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`
  - Fallbacks: `us-gaap:PaymentsToAcquireProductiveAssets`, `us-gaap:PaymentsToAcquireFixedAssets`, `us-gaap:PaymentsToAcquireOtherPropertyPlantAndEquipment`
- Proceeds PP&E (optional): `us-gaap:ProceedsFromSaleOfPropertyPlantAndEquipment`
- FCF (conservative): `CFO − Capex` (optionally show net capex by adding proceeds separately)
- Do not subtract: `us-gaap:PaymentsToAcquireBusinessesNetOfCashAcquired`

3) Balance Sheet Metrics (Net Debt, Liquidity)
- Cash and equivalents (priority): `us-gaap:CashAndCashEquivalentsAtCarryingValue`
  - Useful additions: `us-gaap:RestrictedCashAndCashEquivalentsAtCarryingValue`, `us-gaap:RestrictedCashAndCashEquivalentsCurrent`, `us-gaap:RestrictedCashAndCashEquivalentsNoncurrent`
- Debt components (priority): `us-gaap:LongTermDebtCurrent`, `us-gaap:LongTermDebtNoncurrent`
  - Additions/fallbacks: `us-gaap:ShortTermBorrowings`, `us-gaap:DebtCurrent`, `us-gaap:LongTermDebtAndCapitalLeaseObligationsCurrent`, `us-gaap:LongTermDebtAndCapitalLeaseObligations`
- Net debt (conservative): `total_debt − (cash + optional restricted cash)`; be explicit if restricted cash included
- Current ratio: `us-gaap:AssetsCurrent` / `us-gaap:LiabilitiesCurrent`

4) Coverage and EBITDA‑ish
- Interest expense (priority): `us-gaap:InterestExpense`
  - Fallbacks: `us-gaap:InterestExpenseNonoperating` (P&L), `us-gaap:InterestPaid` (cash flow; contextual)
- Coverage (primary): `OperatingIncomeLoss / InterestExpense`
  - If EBIT ≤ 0 or missing: “Not meaningful/Not available”
- D&A: `us-gaap:DepreciationDepletionAndAmortization`
  - Fallbacks: `us-gaap:DepreciationAndAmortization`, `us-gaap:Depreciation`, `us-gaap:AmortizationOfIntangibleAssets`
- EBITDA (approx.): `OperatingIncomeLoss + D&A` (label as approximation)

5) ROIC (GAAP‑Based Approximation)
- NOPAT ≈ `OperatingIncomeLoss * (1 − effective_tax_rate)`
  - `effective_tax_rate` ≈ `IncomeTaxExpenseBenefit / IncomeLossFromContinuingOperationsBeforeIncomeTaxes`
- Invested Capital ≈ `(TotalAssets − Cash) − (CurrentLiabilities − ShortTermDebt)` (style may vary)
- Core tags: `us-gaap:Assets`, `us-gaap:LiabilitiesCurrent`, `us-gaap:CashAndCashEquivalentsAtCarryingValue`, `us-gaap:ShortTermBorrowings`, `us-gaap:IncomeTaxExpenseBenefit`, `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxes`, `us-gaap:OperatingIncomeLoss`
- Treat ROIC as supporting; always show the exact formula used.

6) GAAP vs Non‑GAAP
- Allowed for scoring: GAAP XBRL facts and derived‑from‑GAAP metrics (clearly labeled).
- Supplemental only: company non‑GAAP (must be labeled and cited; never overrides GAAP).
- Not allowed: invented adjustments or un‑reconciled scraped non‑GAAP.

7) Implementation Pattern
For each metric define:
- `primary_tags`, `fallback_tags`
- `compute_if_missing` formula
- `quality_checks` (e.g., zero/negative guards)
Example (FCF):
- CFO: `NetCashProvidedByUsedInOperatingActivities`
- Capex: `PaymentsToAcquirePropertyPlantAndEquipment` with fallbacks
- FCF: `CFO − Capex`

