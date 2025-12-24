"""SEC data access and helpers (MVP implementation of Step 3).

Implements SEC filings retrieval using the submissions API:
- Latest 10-K
- Last 2–3 10-Q filings
- 8-K filings from the last 90 days
- Form 4 filings from the last 24 months
- Latest DEF 14A (proxy)

Stores metadata JSON and provides raw document URLs (download optional later).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional


def _normalize_cik(cik: str) -> str:
    digits = re.sub(r"\D", "", str(cik))
    return digits.zfill(10)


def _cik_nodash(cik: str) -> str:
    return re.sub(r"\D", "", str(cik)).lstrip("0") or "0"


@dataclass
class Filing:
    form: str
    filingDate: str
    accessionNumber: str
    primaryDocument: Optional[str] = None
    reportDate: Optional[str] = None
    filingUrl: Optional[str] = None
    indexUrl: Optional[str] = None


class SECClient:
    def __init__(self, user_agent: str):
        try:
            import requests  # import here to avoid hard dependency on module import
        except ImportError as e:
            raise RuntimeError(
                "Missing dependency 'requests'. Install it (e.g., 'uv add requests')."
            ) from e

        self._requests = requests
        self.sess = requests.Session()
        self.sess.headers.update({
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        })

    def get_json(self, url: str) -> Dict[str, Any]:
        from time import sleep

        for attempt in range(5):
            r = self.sess.get(url, timeout=30)
            if r.status_code == 429:
                sleep(1 + attempt)
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"Too many 429 responses from SEC for {url}")


def _zip_recent_filings(recent: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    keys = [
        "form",
        "filingDate",
        "accessionNumber",
        "primaryDocument",
        "reportDate",
    ]
    n = len(recent.get("form", []))
    rows: List[Dict[str, Any]] = []
    for i in range(n):
        row = {k: recent.get(k, [None] * n)[i] for k in keys}
        rows.append(row)
    return rows


def _attach_urls(cik10: str, row: Dict[str, Any]) -> Filing:
    acc_no = (row.get("accessionNumber") or "").replace("-", "")
    primary = row.get("primaryDocument")
    base = f"https://www.sec.gov/Archives/edgar/data/{_cik_nodash(cik10)}/{acc_no}"
    filing_url = f"{base}/{primary}" if primary else None
    index_url = f"{base}-index.html"
    return Filing(
        form=row.get("form"),
        filingDate=row.get("filingDate"),
        accessionNumber=row.get("accessionNumber"),
        primaryDocument=primary,
        reportDate=row.get("reportDate"),
        filingUrl=filing_url,
        indexUrl=index_url,
    )


def fetch_filings(
    *,
    cik: str,
    out_root: Path,
    user_agent: str,
    form4_lookback_months: int = 24,
    recent_q_count: int = 3,
) -> Dict[str, Any]:
    """Fetch required filings for a CIK and persist metadata.

    Returns a dict with selected filings and cache paths.
    """
    cik10 = _normalize_cik(cik)
    client = SECClient(user_agent=user_agent)

    cache_dir = out_root / ".cache" / "sec" / cik10
    cache_dir.mkdir(parents=True, exist_ok=True)

    # 1) Load submissions summary
    subs_url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
    subs = client.get_json(subs_url)
    (cache_dir / "submissions.json").write_text(
        json.dumps(subs, indent=2), encoding="utf-8"
    )

    company_name = subs.get("name")
    recent = subs.get("filings", {}).get("recent", {})
    recent_rows = _zip_recent_filings(recent)

    # 2) Optionally load additional year files to extend history (esp. for Form 4)
    history_rows: List[Dict[str, Any]] = []
    files = subs.get("filings", {}).get("files", []) or []
    # Fetch only last two years or those within lookback window
    cutoff_date = datetime.utcnow().date() - timedelta(days=30 * form4_lookback_months)
    for fmeta in files[-3:]:  # last few files are most recent years
        name = fmeta.get("name")
        if not name:
            continue
        # Expect paths like CIK0000320193-2024.json
        url = f"https://data.sec.gov/submissions/{name}"
        try:
            year_json = client.get_json(url)
        except Exception:
            continue
        for row in year_json.get("filings", []):
            # Each row is a dict with similar keys
            try:
                # Filter by date roughly to reduce volume
                fdate = row.get("filingDate")
                if fdate and datetime.strptime(fdate, "%Y-%m-%d").date() < cutoff_date:
                    # keep anyway; we will filter later per form
                    pass
            except Exception:
                pass
            history_rows.append(row)

    all_rows = recent_rows + history_rows

    # 3) Build Filing objects with URLs
    filings: List[Filing] = [_attach_urls(cik10, r) for r in all_rows]

    # 4) Select required sets
    def by_form(form: str) -> List[Filing]:
        return [f for f in filings if (f.form or "").upper() == form.upper()]

    def first_by_form(form: str) -> Optional[Filing]:
        xs = by_form(form)
        xs.sort(key=lambda x: x.filingDate or "", reverse=True)
        return xs[0] if xs else None

    # Latest 10-K
    latest_10k = first_by_form("10-K")

    # Last N 10-Q
    q_filings = by_form("10-Q")
    q_filings.sort(key=lambda x: x.filingDate or "", reverse=True)
    latest_qs = q_filings[: max(0, recent_q_count)]

    # 8-K in last 90 days
    cutoff_8k = datetime.utcnow().date() - timedelta(days=90)
    k_filings = [f for f in filings if (f.form or "").upper() == "8-K"]
    recent_8ks = []
    for f in k_filings:
        try:
            if f.filingDate and datetime.strptime(f.filingDate, "%Y-%m-%d").date() >= cutoff_8k:
                recent_8ks.append(f)
        except Exception:
            pass

    # DEF 14A latest
    def14a = first_by_form("DEF 14A")

    # Form 4 last N months (include 4 and 4/A)
    cutoff_4 = datetime.utcnow().date() - timedelta(days=30 * form4_lookback_months)
    f4_filings = [f for f in filings if (f.form or "").upper() in ("4", "4/A")]
    f4_window = []
    for f in f4_filings:
        try:
            if f.filingDate and datetime.strptime(f.filingDate, "%Y-%m-%d").date() >= cutoff_4:
                f4_window.append(f)
        except Exception:
            pass

    # 5) Persist metadata selection
    def _as_dict(f: Optional[Filing]) -> Optional[Dict[str, Any]]:
        if not f:
            return None
        return {
            "form": f.form,
            "filingDate": f.filingDate,
            "accessionNumber": f.accessionNumber,
            "primaryDocument": f.primaryDocument,
            "filingUrl": f.filingUrl,
            "indexUrl": f.indexUrl,
        }

    selected = {
        "10-K": _as_dict(latest_10k),
        "10-Q": [
            _as_dict(x) for x in latest_qs
        ],
        "8-K": [_as_dict(x) for x in recent_8ks],
        "DEF 14A": _as_dict(def14a),
        "4": [_as_dict(x) for x in f4_window],
    }

    meta = {
        "cik": cik10,
        "companyName": company_name,
        "selected": selected,
        "counts": {
            "total": len(filings),
            "10-Q": len(latest_qs),
            "8-K_90d": len(recent_8ks),
            "4_lookback": len(f4_window),
        },
    }

    meta_path = cache_dir / "filings_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return {
        "selected": selected,
        "cache_paths": {
            "metadata": str(meta_path),
            "submissions": str(cache_dir / "submissions.json"),
        },
    }


# Placeholder for Step 4 extraction entry to keep API consistent with imports elsewhere
def extract_xbrl_timeseries(
    *, cik: str, out_root: Path, user_agent: str
) -> Dict[str, Any]:
    """Extract structured financial timeseries from SEC Company Facts API.

    Returns dict with per-metric series and output paths. Persists a combined
    tidy timeseries file (Parquet if available, else JSON).
    """
    cik10 = _normalize_cik(cik)
    client = SECClient(user_agent=user_agent)
    cache_dir = out_root / ".cache" / "sec" / cik10
    cache_dir.mkdir(parents=True, exist_ok=True)

    facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
    facts = client.get_json(facts_url)
    facts_json = json.dumps(facts, indent=2)
    facts_path_primary = cache_dir / "companyfacts.json"
    try:
        facts_path_primary.write_text(facts_json, encoding="utf-8")
        facts_path_str = str(facts_path_primary)
    except Exception:
        # Windows path edge cases: fall back to a shorter, flat path
        fallback_dir = out_root / ".cache" / "sec"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        facts_path_fallback = fallback_dir / f"companyfacts_{cik10}.json"
        facts_path_fallback.write_text(facts_json, encoding="utf-8")
        facts_path_str = str(facts_path_fallback)

    def get_facts(tag: str) -> Optional[Dict[str, Any]]:
        # facts["facts"]["us-gaap"][tag]
        try:
            taxonomy, t = tag.split(":", 1)
        except ValueError:
            taxonomy, t = "us-gaap", tag
        node = facts.get("facts", {}).get(taxonomy, {}).get(t)
        return node

    def extract_series(tag_list: List[str], unit_prefs: List[str]) -> (List[Dict[str, Any]], Optional[str], Optional[str]):
        # returns (series, chosen_tag, chosen_unit)
        for tag in tag_list:
            node = get_facts(tag)
            if not node:
                continue
            units = node.get("units", {})
            # Try preferred units in order
            for unit in unit_prefs:
                entries = units.get(unit)
                if not entries:
                    continue
                # Normalize by end date, keep latest filed per end
                best_by_end: Dict[str, Dict[str, Any]] = {}
                for e in entries:
                    end = e.get("end") or e.get("date")
                    val = e.get("val")
                    if end is None or val is None:
                        continue
                    filed = e.get("filed") or ""
                    cur = best_by_end.get(end)
                    if cur is None or (filed and filed > (cur.get("filed") or "")):
                        best_by_end[end] = e
                # Build tidy rows
                rows: List[Dict[str, Any]] = []
                for end, e in best_by_end.items():
                    rows.append(
                        {
                            "end": end,
                            "val": e.get("val"),
                            "fy": e.get("fy"),
                            "fp": e.get("fp"),
                            "form": e.get("form"),
                            "accn": e.get("accn"),
                            "filed": e.get("filed"),
                            "tag": tag,
                            "unit": unit,
                        }
                    )
                # Sort by end date
                rows.sort(key=lambda r: r["end"] or "")
                if rows:
                    return rows, tag, unit
        return [], None, None

    # Define tag priority according to the plan
    tags = {
        "revenue": [
            "us-gaap:Revenues",
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap:SalesRevenueNet",
            "us-gaap:SalesRevenueGoodsNet",
            "us-gaap:SalesRevenueServicesNet",
            # Financials model fallbacks could be handled later
        ],
        "cost_of_revenue": [
            "us-gaap:CostOfRevenue",
            "us-gaap:CostOfGoodsAndServicesSold",
            "us-gaap:CostOfGoodsSold",
            "us-gaap:CostOfServices",
        ],
        "gross_profit": [
            "us-gaap:GrossProfit",
        ],
        "operating_income": [
            "us-gaap:OperatingIncomeLoss",
            "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
        ],
        "net_income": [
            "us-gaap:NetIncomeLoss",
            "us-gaap:ProfitLoss",
            "us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic",
        ],
        "diluted_shares": [
            "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
            "us-gaap:WeightedAverageNumberOfSharesOutstandingDiluted",
            "us-gaap:CommonStockSharesOutstanding",
        ],
        "cfo": [
            "us-gaap:NetCashProvidedByUsedInOperatingActivities",
            "us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ],
        "capex": [
            "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
            "us-gaap:PaymentsToAcquireProductiveAssets",
            "us-gaap:PaymentsToAcquireFixedAssets",
            "us-gaap:PaymentsToAcquireOtherPropertyPlantAndEquipment",
        ],
        "proceeds_ppe": [
            "us-gaap:ProceedsFromSaleOfPropertyPlantAndEquipment",
        ],
        "cash": [
            "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        ],
        "restricted_cash": [
            "us-gaap:RestrictedCashAndCashEquivalentsAtCarryingValue",
            "us-gaap:RestrictedCashAndCashEquivalentsCurrent",
            "us-gaap:RestrictedCashAndCashEquivalentsNoncurrent",
        ],
        "lt_debt_current": [
            "us-gaap:LongTermDebtCurrent",
        ],
        "lt_debt_noncurrent": [
            "us-gaap:LongTermDebtNoncurrent",
        ],
        "short_term_borrowings": [
            "us-gaap:ShortTermBorrowings",
            "us-gaap:DebtCurrent",
        ],
        "assets_current": [
            "us-gaap:AssetsCurrent",
        ],
        "liabilities_current": [
            "us-gaap:LiabilitiesCurrent",
        ],
        "interest_expense": [
            "us-gaap:InterestExpense",
            "us-gaap:InterestExpenseNonoperating",
        ],
        "depreciation_amortization": [
            "us-gaap:DepreciationDepletionAndAmortization",
            "us-gaap:DepreciationAndAmortization",
            "us-gaap:Depreciation",
            "us-gaap:AmortizationOfIntangibleAssets",
        ],
        "assets_total": [
            "us-gaap:Assets",
        ],
        "income_tax_expense": [
            "us-gaap:IncomeTaxExpenseBenefit",
        ],
        "pretax_income": [
            "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
        ],
        "short_term_debt": [
            "us-gaap:ShortTermBorrowings",
        ],
    }

    # Unit preferences per metric
    USD = ["USD", "usd"]
    SHARES = ["shares", "SHARES"]
    PURE = ["pure"]
    unit_prefs = {
        "revenue": USD,
        "cost_of_revenue": USD,
        "gross_profit": USD,
        "operating_income": USD,
        "net_income": USD,
        "diluted_shares": SHARES,
        "cfo": USD,
        "capex": USD,
        "proceeds_ppe": USD,
        "cash": USD,
        "restricted_cash": USD,
        "lt_debt_current": USD,
        "lt_debt_noncurrent": USD,
        "short_term_borrowings": USD,
        "assets_current": USD,
        "liabilities_current": USD,
        "interest_expense": USD,
        "depreciation_amortization": USD,
        "assets_total": USD,
        "income_tax_expense": USD,
        "pretax_income": USD,
        "short_term_debt": USD,
    }

    series: Dict[str, List[Dict[str, Any]]] = {}
    provenance: Dict[str, Dict[str, str]] = {}

    for metric, tag_list in tags.items():
        rows, chosen_tag, chosen_unit = extract_series(tag_list, unit_prefs.get(metric, USD))
        if rows:
            series[metric] = rows
            provenance[metric] = {"tag": chosen_tag or "", "unit": chosen_unit or ""}
        else:
            series[metric] = []
            provenance[metric] = {"tag": "", "unit": ""}

    # Derived: gross_profit if missing and both revenue + cost_of_revenue present
    if not series.get("gross_profit") and series.get("revenue") and series.get("cost_of_revenue"):
        # Map by end date
        rev = {r["end"]: r for r in series["revenue"]}
        cogs = {r["end"]: r for r in series["cost_of_revenue"]}
        rows: List[Dict[str, Any]] = []
        for end, r in rev.items():
            if end in cogs and r.get("val") is not None and cogs[end].get("val") is not None:
                rows.append(
                    {
                        "end": end,
                        "val": r["val"] - cogs[end]["val"],
                        "fy": r.get("fy"),
                        "fp": r.get("fp"),
                        "form": r.get("form"),
                        "accn": r.get("accn"),
                        "filed": r.get("filed"),
                        "tag": "derived:gross_profit",
                        "unit": provenance["revenue"]["unit"] or "USD",
                    }
                )
        rows.sort(key=lambda r: r["end"] or "")
        series["gross_profit"] = rows
        provenance["gross_profit"] = {"tag": "derived:revenue-cost_of_revenue", "unit": "USD"}

    # Derived: total debt
    def _to_map(key: str) -> Dict[str, Dict[str, Any]]:
        return {r["end"]: r for r in series.get(key, [])}

    lt_cur = _to_map("lt_debt_current")
    lt_non = _to_map("lt_debt_noncurrent")
    stb = _to_map("short_term_borrowings")
    rows_td: List[Dict[str, Any]] = []
    date_keys = set(lt_cur.keys()) | set(lt_non.keys()) | set(stb.keys())
    for end in sorted(date_keys):
        val = 0.0
        for m in (lt_cur, lt_non, stb):
            if end in m and m[end].get("val") is not None:
                val += float(m[end]["val"])
        rows_td.append(
            {
                "end": end,
                "val": val,
                "fy": lt_cur.get(end, lt_non.get(end, stb.get(end, {}))).get("fy"),
                "fp": lt_cur.get(end, lt_non.get(end, stb.get(end, {}))).get("fp"),
                "form": lt_cur.get(end, lt_non.get(end, stb.get(end, {}))).get("form"),
                "accn": lt_cur.get(end, lt_non.get(end, stb.get(end, {}))).get("accn"),
                "filed": lt_cur.get(end, lt_non.get(end, stb.get(end, {}))).get("filed"),
                "tag": "derived:total_debt",
                "unit": "USD",
            }
        )
    series["total_debt"] = rows_td
    provenance["total_debt"] = {"tag": "derived:sum(lt_debt_current,lt_debt_noncurrent,short_term_borrowings)", "unit": "USD"}

    # Persist tidy timeseries
    timeseries_rows: List[Dict[str, Any]] = []
    for metric, rows in series.items():
        for r in rows:
            timeseries_rows.append({"metric": metric, **r})

    ts_path_parquet = cache_dir / "timeseries.parquet"
    ts_path_json = cache_dir / "timeseries.json"

    saved_path: Optional[str] = None
    # Try Parquet first
    try:
        import pandas as pd  # type: ignore
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore

        df = pd.DataFrame(timeseries_rows)
        if not df.empty:
            table = pa.Table.from_pandas(df)
            pq.write_table(table, ts_path_parquet)
            saved_path = str(ts_path_parquet)
        else:
            ts_path_json.write_text(json.dumps(timeseries_rows, indent=2), encoding="utf-8")
            saved_path = str(ts_path_json)
    except Exception:
        # Fallback to JSON
        ts_path_json.write_text(json.dumps(timeseries_rows, indent=2), encoding="utf-8")
        saved_path = str(ts_path_json)

    return {
        "series": series,
        "provenance": provenance,
        "paths": {
            "facts": facts_path_str,
            "timeseries": saved_path,
        },
    }
