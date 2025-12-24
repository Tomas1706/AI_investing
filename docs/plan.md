ONE-SHOT VALUE INVESTING RESEARCH SCRIPT – FULL IMPLEMENTATION PLAN

Purpose
Build a Python script that runs on demand for a single US stock ticker and produces a long-term, value-investing research report as a text file.

The script answers this question:

“Is this a durable business worth owning for many years at a reasonable price, based on conservative, evidence-based analysis?”

The script is not periodic. It runs once when invoked.

1. User interaction and execution
The script is executed from the command line.

Example command:
python run.py --ticker AAPL

Optional arguments:
--out <directory> (default: reports/)
--asof <YYYY-MM-DD> (default: today)
--no-web (skip Bright Data MCP and web sources)

The script always produces an output file unless the ticker is invalid or non-US.

Output file path:
reports/AAPL_YYYY-MM-DD.txt

2.Core rules the script must obey
-SEC data is the primary source of truth
-Public web data is secondary and contextual
-No numbers may be invented
-Every numeric metric must have a source
-If data is missing, say “Not available”
-Facts are extracted first, narrative is written last
-The tone must be conservative and long-term
-The result is not “buy/sell”, but:
-Investigate Further
-Watch
-Avoid-for-now

3. High-level execution flow
-When run.py executes, it must do the following steps in order:
-Resolve ticker → CIK
-Download relevant SEC filings
-Extract structured financial data from SEC
-Compute value-oriented financial metrics
-Analyze insider activity (Form 4)
-Assemble a complete SEC evidence bundle
-Optionally retrieve web context via Bright Data MCP
-Validate and filter web data
-Convert facts into normalized value signals
-Compute a conservative long-term score
-Ask an LLM to write a value-investing memo
-Write the final report to a text file
-Each step must be callable and testable independently.

4.Files and modules Codex should create
-At minimum, the codebase should contain:
-run.py
-config.py
-sec.py
-metrics.py
-insiders.py
-web.py
-web_validate.py
-analysis.py
-scoring.py
-llm.py
-report.py
-cache.py (optional but recommended)
Codex may split these further, but responsibilities should remain equivalent.

5. Step 1 – Ticker resolution (US only)
-Input: ticker string (e.g., “AAPL”)
-Action:
--Look up the ticker in SEC data
--Resolve it to a CIK and official company name
Rules:
--If the ticker does not exist or is not US-listed, exit with a clear error
--Cache the ticker → CIK mapping locally
Output:
--cik
--company_name

6. Step 2 – SEC filings retrieval
For the resolved CIK, retrieve:
-Latest 10-K
-Last 2–3 10-Q filings
-Any 8-K filings from the last 90 days
-All Form 4 filings from the last 12–24 months
-Latest DEF 14A (proxy statement), if available

For each filing, store:
-Form type
-Filing date
-Accession number
-SEC URL
-Raw filing text
-If a filing type is unavailable, continue with others.

7. Step 3 – Structured SEC financial data extraction
From SEC XBRL or structured endpoints, extract:
-Income statement history
-Balance sheet history
-Cash flow statement history
-Diluted shares outstanding history
-Segment revenue (if disclosed)
-Normalize all data into numeric time series indexed by fiscal period.

Step 4 – Deterministic metric computation (no LLM)
Using only Python logic, compute long-term value metrics.
Business durability:
-Revenue CAGR (multi-year)
-Revenue drawdowns in weak years
-Segment concentration flags
-Customer concentration flags (from filings)

Economic moat proxies:
-Gross margin level
-Gross margin stability over time
-Operating margin trend
-ROIC or ROE persistence

Financial strength:
Net debt / EBITDA (or net debt / FCF fallback)
-Interest coverage ratio
-Current ratio
-Free cash flow consistency
-Capital allocation:

Free cash flow usage breakdown:
-reinvestment (capex)
-buybacks
-dividends
-debt reduction
-acquisitions
-Share count trend (dilution vs reduction)
-Stock-based compensation as % of revenue (if available)

Each metric must include provenance:
-Source filing
-Filing date
-Accession number
-SEC URL

8. Step 5 – Insider activity analysis (Form 4)
Parse Form 4 filings to compute:
Net shares bought or sold over:
-3 months
-6 months
-12 months
-Number of unique insiders buying vs selling
-Detection of clustered activity
-Executive weighting (CEO, CFO, Chair matter more)
-Simple routine-selling heuristic
-Produce a summarized insider behavior assessment focused on owner alignment.

9. Step 6 – SEC evidence bundle
Combine all SEC-derived information into a single structured object:
-Company identity
-Financial metrics
-Insider summary
-Extracted factual claims from filings
-Citations and evidence snippets
-This object is immutable and becomes the primary factual input for later steps.

10. Step 7 – Public web supplement (optional)
If web is enabled, retrieve additional context using Bright Data MCP.
Web data should be used ONLY to support long-term value questions:
-Competitive landscape and market structure
-Market share commentary (if reputable)
-Long-term regulatory or legal risks
-Durable demand drivers
-Current stock price / market cap (if not using an API)
-Rules:
-Limit total scraped pages (default max: 8)
-Prefer reputable sources (company IR, regulators, major finance outlets)
-Avoid hype, price targets, or social sentiment

11. Step 8 – Web data extraction and validation
Extract web claims using a strict schema:
For every claim:
-Claim text
-Source URL
-Supporting quote/snippet
-Confidence level
Validation rules:
-Numeric claims require strong sources
-Prefer multiple sources for numbers
-Downweight web signals vs SEC signals
-Discard low-quality or speculative sources

12. Step 9 – Signal construction
Convert metrics and claims into normalized signals.
Each signal must include:
-Name
-Raw value
-Normalized score (0–1)
-Weight
-Evidence references
Signals should emphasize:
-Durability
-Moat persistence
-Balance sheet protection
-Capital allocation discipline
-Margin of safety

13. Step 10 – Long-term value scoring and classification
Compute category scores using conservative weights:
-Business durability
-Moat and ROIC persistence
-Financial strength
-Capital allocation quality
-Valuation
-Insider alignment
Apply red-flag overrides:
-Severe red flags force “Avoid-for-now”
Final classification:
-Investigate Further
-Watch
-Avoid-for-now
Also compute a confidence level:
-High
-Medium
-Low

14. Step 11 – LLM synthesis (memo writing only)
Pass the following to the LLM:
-SEC evidence bundle
-Validated web claims
-Computed metrics and scores

Final classification
The LLM must:
-Write a sober, long-term value-investing memo
-Explain reasoning clearly
-Highlight uncertainty and risks
-Avoid introducing new numbers
-Explicitly state what could break the thesis

15. Step 12 – Report generation
Generate a plain text report with these sections:
-Business overview
-Business durability and moat
-Financial strength
-Capital allocation and management behavior
-Insider activity
-Valuation and margin of safety
-Key risks and failure modes
-Long-term verdict and confidence
-What would change my mind
-Sources and citations
-Write the file to disk.

16. Error handling and guarantees
If the ticker is invalid or non-US: exit early with message
If some data fails to load: continue and note missing sections
Always produce an output file if the ticker is valid
Never silently ignore missing data

17. Implementation order Codex should follow
Phase 1:
Ticker → CIK
SEC filings retrieval
Metric computation
Insider analysis
Text report (SEC only)

Phase 2:
Add valuation using price data

Phase 3:
Add Bright Data MCP web context