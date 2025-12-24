"""Optional web-based metrics extractors.

Yahoo Finance extractor: uses yfinance if available to pull basic financials
and map to the same metric schema used by SEC-derived metrics.

Bright Data MCP (later): a placeholder stub to be wired to MCP's API.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import json


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "").replace("&", "and")


def fetch_yahoo_metrics(*, ticker: str, out_root: Path) -> Dict[str, Any]:
    """Fetch metrics from Yahoo Finance via yfinance.

    Returns a dict with a 'metrics' mapping and a 'paths' mapping.
    Persists JSON under reports/.cache/web/yahoo/<TICKER>/metrics.json

    Requires 'yfinance' to be installed. If missing, raises a RuntimeError
    with guidance to install it.
    """
    try:
        import yfinance as yf  # type: ignore
        import pandas as pd  # noqa: F401
    except Exception as e:
        raise RuntimeError(
            "Missing dependency 'yfinance'. Install it (e.g., 'uv add yfinance')."
        ) from e

    t = yf.Ticker(ticker)

    fin = t.financials or None
    bsh = t.balance_sheet or None
    cfs = t.cashflow or None
    info = getattr(t, "info", {}) or {}

    def latest_from_df(df, key_names, default=None, abs_value=False):
        if df is None or df.empty:
            return default
        # Find row by normalized name
        idx_map = { _norm(str(i)): i for i in df.index }
        row_key = None
        for name in key_names:
            k = _norm(name)
            if k in idx_map:
                row_key = idx_map[k]
                break
        if row_key is None:
            return default
        # Pick the latest column value
        try:
            val = df.loc[row_key].dropna()
            if val.shape[0] == 0:
                return default
            v = float(val.iloc[0])
            return abs(v) if abs_value else v
        except Exception:
            return default

    # Map metrics
    revenue = latest_from_df(fin, ["Total Revenue"])  # USD
    cost_of_revenue = latest_from_df(fin, ["Cost Of Revenue"])  # USD
    gross_profit = latest_from_df(fin, ["Gross Profit"])  # USD
    operating_income = latest_from_df(fin, ["Operating Income"])  # USD
    net_income = latest_from_df(fin, ["Net Income"])  # USD
    interest_expense = latest_from_df(fin, ["Interest Expense"])  # USD

    # CFO and CapEx from cashflow; CapEx often negative in Yahoo (cash outflow)
    cfo = latest_from_df(cfs, ["Total Cash From Operating Activities"])  # USD
    capex = latest_from_df(cfs, ["Capital Expenditures"], abs_value=True)  # USD (positive)

    # D&A appears in financials cashflow as separate lines; try a few labels
    d_and_a = latest_from_df(
        cfs,
        [
            "Depreciation",
            "Depreciation And Amortization",
            "Amortization",
            "Depreciation Amortization",
        ],
    )
    if d_and_a is None:
        d_and_a = latest_from_df(fin, ["Depreciation & Amortization"])  # sometimes here

    # Balance sheet items
    assets_current = latest_from_df(bsh, ["Total Current Assets"])  # USD
    liabilities_current = latest_from_df(bsh, ["Total Current Liabilities"])  # USD
    cash = latest_from_df(bsh, ["Cash And Cash Equivalents"])  # USD
    short_lt_debt = latest_from_df(bsh, ["Short Long Term Debt", "Short Term Borrowings"])  # USD
    long_term_debt = latest_from_df(bsh, ["Long Term Debt"])  # USD
    total_debt = None
    try:
        total_debt = (short_lt_debt or 0.0) + (long_term_debt or 0.0)
    except Exception:
        total_debt = None

    # Shares outstanding
    shares_out = None
    for k in ("sharesOutstanding", "impliedSharesOutstanding", "impliedSharesOutstandingPreviousClose"):
        v = info.get(k)
        if v:
            try:
                shares_out = float(v)
                break
            except Exception:
                pass

    # EBITDA approx (GAAP-derived style) for comparison
    ebitda_approx = None
    try:
        if operating_income is not None and d_and_a is not None:
            ebitda_approx = float(operating_income) + float(d_and_a)
    except Exception:
        pass

    data = {
        "source": "yahoo",
        "ticker": ticker,
        "asof": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "metrics": {
            "revenue": revenue,
            "cost_of_revenue": cost_of_revenue,
            "gross_profit": gross_profit,
            "operating_income": operating_income,
            "net_income": net_income,
            "interest_expense": interest_expense,
            "cfo": cfo,
            "capex": capex,
            "depreciation_amortization": d_and_a,
            "assets_current": assets_current,
            "liabilities_current": liabilities_current,
            "cash": cash,
            "total_debt": total_debt,
            "shares_outstanding": shares_out,
            "ebitda_approx": ebitda_approx,
        },
    }

    # Persist
    out_dir = out_root / ".cache" / "web" / "yahoo" / ticker.upper()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "metrics.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    return {"metrics": data["metrics"], "paths": {"metrics": str(path)}}


def fetch_bright_mcp_metrics(*, ticker: str, api_base: str, api_key: str, out_root: Path) -> Dict[str, Any]:
    """Placeholder for Bright Data MCP metrics extraction.

    Expected behavior (to implement when credentials and endpoint spec available):
    - Query MCP for authoritative sources (IR pages, 10-K/10-Q exhibits, regulator sites).
    - Extract the same metrics as the SEC/Yahoo paths with citations and confidence.
    - Persist JSON under reports/.cache/web/bright_mcp/<TICKER>/metrics.json

    Currently returns a NotImplemented error.
    """
    raise NotImplementedError(
        "Bright MCP integration not implemented yet. Provide API spec/SDK to proceed."
    )


def fetch_alpha_vantage_metrics(*, ticker: str, api_key: str, out_root: Path) -> Dict[str, Any]:
    """Fetch metrics using Alpha Vantage fundamental endpoints.

    Endpoints used:
    - INCOME_STATEMENT
    - BALANCE_SHEET
    - CASH_FLOW
    - OVERVIEW (for shares outstanding)

    Returns a dict {metrics, paths} and persists JSON under
    reports/.cache/web/alpha_vantage/<TICKER>/metrics.json
    """
    if not api_key:
        raise RuntimeError(
            "Missing ALPHAVANTAGE_API_KEY. Set it in .env or environment."
        )
    try:
        import requests  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Missing dependency 'requests'. Install it (e.g., 'uv add requests')."
        ) from e

    import time
    base = "https://www.alphavantage.co/query"

    def get(function: str) -> Dict[str, Any]:
        params = {"function": function, "symbol": ticker.upper(), "apikey": api_key}
        # Simple retry with per-request throttling (1.2s) to respect free tier
        last_exc: Optional[Exception] = None
        for attempt in range(5):
            try:
                r = requests.get(base, params=params, timeout=30)
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict) and (data.get("Note") or data.get("Information")):
                    # Rate limited or guidance; sleep longer and retry
                    time.sleep(2 + attempt)
                    last_exc = RuntimeError(data.get("Note") or data.get("Information"))
                    continue
                # Polite sleep between successful calls
                time.sleep(1.2)
                return data
            except Exception as e:
                last_exc = e
                time.sleep(1.2 + attempt)
        raise RuntimeError(f"Alpha Vantage request failed for {function}: {last_exc}")

    def num(x):
        try:
            return float(x)
        except Exception:
            return None

    income = get("INCOME_STATEMENT")
    balance = get("BALANCE_SHEET")
    cash = get("CASH_FLOW")
    overview = get("OVERVIEW")

    inc_a = (income.get("annualReports") or [])
    bal_a = (balance.get("annualReports") or [])
    cfs_a = (cash.get("annualReports") or [])
    latest_inc = inc_a[0] if inc_a else {}
    latest_bal = bal_a[0] if bal_a else {}
    latest_cfs = cfs_a[0] if cfs_a else {}

    fiscal_end = latest_inc.get("fiscalDateEnding") or latest_bal.get("fiscalDateEnding") or latest_cfs.get("fiscalDateEnding")

    revenue = num(latest_inc.get("totalRevenue"))
    cost_of_revenue = num(latest_inc.get("costOfRevenue"))
    gross_profit = num(latest_inc.get("grossProfit"))
    operating_income = num(latest_inc.get("operatingIncome"))
    net_income = num(latest_inc.get("netIncome"))
    interest_expense = num(latest_inc.get("interestExpense"))
    d_and_a = num(latest_inc.get("depreciationAndAmortization"))

    operating_cashflow = num(latest_cfs.get("operatingCashflow"))
    capex = latest_cfs.get("capitalExpenditures")
    capex_val = num(capex)
    if capex_val is not None:
        capex_val = abs(capex_val)  # report positive outflow to align with SEC convention

    assets_current = num(latest_bal.get("totalCurrentAssets"))
    liabilities_current = num(latest_bal.get("totalCurrentLiabilities"))
    cash_ce = num(latest_bal.get("cashAndCashEquivalentsAtCarryingValue") or latest_bal.get("cashAndCashEquivalents"))
    short_debt = num(latest_bal.get("shortTermDebt") or latest_bal.get("shortLongTermDebtTotal"))
    long_debt = num(latest_bal.get("longTermDebt"))
    total_debt = None
    if short_debt is not None or long_debt is not None:
        total_debt = (short_debt or 0.0) + (long_debt or 0.0)

    shares_out = num(overview.get("SharesOutstanding"))

    ebitda_approx = None
    if operating_income is not None and d_and_a is not None:
        try:
            ebitda_approx = float(operating_income) + float(d_and_a)
        except Exception:
            pass

    data = {
        "source": "alpha_vantage",
        "ticker": ticker.upper(),
        "asof": fiscal_end or datetime.utcnow().date().isoformat(),
        "metrics": {
            "revenue": revenue,
            "cost_of_revenue": cost_of_revenue,
            "gross_profit": gross_profit,
            "operating_income": operating_income,
            "net_income": net_income,
            "interest_expense": interest_expense,
            "cfo": operating_cashflow,
            "capex": capex_val,
            "depreciation_amortization": d_and_a,
            "assets_current": assets_current,
            "liabilities_current": liabilities_current,
            "cash": cash_ce,
            "total_debt": total_debt,
            "shares_outstanding": shares_out,
            "ebitda_approx": ebitda_approx,
        },
    }

    out_dir = out_root / ".cache" / "web" / "alpha_vantage" / ticker.upper()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "metrics.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    return {"metrics": data["metrics"], "paths": {"metrics": str(path)}}


def fetch_alpha_vantage_series(*, ticker: str, api_key: str, out_root: Path) -> Dict[str, Any]:
    """Build series similar to SEC's timeseries using Alpha Vantage annual reports.

    Each series is a list of rows with keys: end, val, fy, fp, form, accn, filed, tag, unit
    Where fp='FY', form='ANNUAL', accn/filed are not available (set to None), unit from reportedCurrency.
    Persists a combined timeseries JSON under reports/.cache/web/alpha_vantage/<TICKER>/timeseries.json
    """
    if not api_key:
        raise RuntimeError(
            "Missing ALPHAVANTAGE_API_KEY. Set it in .env or environment."
        )
    try:
        import requests  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Missing dependency 'requests'. Install it (e.g., 'uv add requests')."
        ) from e

    import time
    base = "https://www.alphavantage.co/query"
    params = {"symbol": ticker.upper(), "apikey": api_key}

    def get(function: str) -> Dict[str, Any]:
        last_exc: Optional[Exception] = None
        for attempt in range(5):
            try:
                r = requests.get(base, params={**params, "function": function}, timeout=30)
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict) and (data.get("Note") or data.get("Information")):
                    time.sleep(2 + attempt)
                    last_exc = RuntimeError(data.get("Note") or data.get("Information"))
                    continue
                time.sleep(1.2)
                return data
            except Exception as e:
                last_exc = e
                time.sleep(1.2 + attempt)
        raise RuntimeError(f"Alpha Vantage request failed for {function}: {last_exc}")

    def rows_from_annual(annual: list, key: str, tag: str) -> list:
        rows = []
        for item in annual:
            val = item.get(key)
            end = item.get("fiscalDateEnding")
            unit = item.get("reportedCurrency") or "USD"
            try:
                v = float(val)
            except Exception:
                continue
            fy = None
            try:
                fy = int((end or "")[:4])
            except Exception:
                pass
            rows.append(
                {
                    "end": end,
                    "val": v,
                    "fy": fy,
                    "fp": "FY",
                    "form": "ANNUAL",
                    "accn": None,
                    "filed": None,
                    "tag": f"alpha_vantage:{tag}",
                    "unit": unit,
                }
            )
        rows.sort(key=lambda r: r["end"] or "")
        return rows

    income = get("INCOME_STATEMENT")
    balance = get("BALANCE_SHEET")
    cash = get("CASH_FLOW")
    inc_a = (income.get("annualReports") or [])
    bal_a = (balance.get("annualReports") or [])
    cfs_a = (cash.get("annualReports") or [])

    series: Dict[str, list] = {}

    # Income statement series
    series["revenue"] = rows_from_annual(inc_a, "totalRevenue", "totalRevenue")
    series["cost_of_revenue"] = rows_from_annual(inc_a, "costOfRevenue", "costOfRevenue")
    series["gross_profit"] = rows_from_annual(inc_a, "grossProfit", "grossProfit")
    series["operating_income"] = rows_from_annual(inc_a, "operatingIncome", "operatingIncome")
    series["net_income"] = rows_from_annual(inc_a, "netIncome", "netIncome")
    series["interest_expense"] = rows_from_annual(inc_a, "interestExpense", "interestExpense")
    # D&A: may appear in income or cash flow; prefer income; if empty, use cash flow
    da_income = rows_from_annual(inc_a, "depreciationAndAmortization", "depreciationAndAmortization")
    da_cash = rows_from_annual(cfs_a, "depreciationAndAmortization", "depreciationAndAmortization")
    series["depreciation_amortization"] = da_income or da_cash

    # Cash flow series
    series["cfo"] = rows_from_annual(cfs_a, "operatingCashflow", "operatingCashflow")
    # CapEx as positive cash outflow
    capex_rows = rows_from_annual(cfs_a, "capitalExpenditures", "capitalExpenditures")
    for r in capex_rows:
        r["val"] = abs(r["val"])  # make positive
    series["capex"] = capex_rows
    # Optional proceeds from PPE
    series["proceeds_ppe"] = rows_from_annual(
        cfs_a, "proceedsFromSaleOfPropertyPlantAndEquipment", "proceedsFromSaleOfPPE"
    )

    # Balance sheet series
    series["assets_current"] = rows_from_annual(bal_a, "totalCurrentAssets", "totalCurrentAssets")
    series["liabilities_current"] = rows_from_annual(bal_a, "totalCurrentLiabilities", "totalCurrentLiabilities")
    series["cash"] = rows_from_annual(
        bal_a,
        "cashAndCashEquivalentsAtCarryingValue",
        "cashAndCashEquivalentsAtCarryingValue",
    ) or rows_from_annual(bal_a, "cashAndCashEquivalents", "cashAndCashEquivalents")
    series["lt_debt_current"] = rows_from_annual(bal_a, "shortTermDebt", "shortTermDebt")
    series["lt_debt_noncurrent"] = rows_from_annual(bal_a, "longTermDebt", "longTermDebt")
    series["short_term_borrowings"] = rows_from_annual(
        bal_a, "shortLongTermDebtTotal", "shortLongTermDebtTotal"
    )  # approximation of short-term borrowings
    series["diluted_shares"] = rows_from_annual(
        bal_a, "commonStockSharesOutstanding", "commonStockSharesOutstanding"
    )

    # Derived total debt
    def _to_map(rows):
        return {r["end"]: r for r in rows}

    lt_cur = _to_map(series.get("lt_debt_current", []))
    lt_non = _to_map(series.get("lt_debt_noncurrent", []))
    stb = _to_map(series.get("short_term_borrowings", []))
    td_rows = []
    keys = sorted(set(lt_cur.keys()) | set(lt_non.keys()) | set(stb.keys()))
    for end in keys:
        v = (lt_cur.get(end, {}).get("val") or 0.0) + (lt_non.get(end, {}).get("val") or 0.0) + (
            stb.get(end, {}).get("val") or 0.0
        )
        fy = None
        try:
            fy = int((end or "")[:4])
        except Exception:
            pass
        td_rows.append(
            {
                "end": end,
                "val": v,
                "fy": fy,
                "fp": "FY",
                "form": "ANNUAL",
                "accn": None,
                "filed": None,
                "tag": "alpha_vantage:total_debt",
                "unit": "USD",
            }
        )
    series["total_debt"] = td_rows

    # Persist combined timeseries
    out_dir = out_root / ".cache" / "web" / "alpha_vantage" / ticker.upper()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "timeseries.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(
            [{"metric": k, **row} for k, rows in series.items() for row in rows], f, indent=2
        )

    return {"series": series, "paths": {"timeseries": str(path)}}


def fetch_alpha_vantage_insider_transactions(*, ticker: str, api_key: str, out_root: Path) -> Dict[str, Any]:
    """Fetch insider transactions using Alpha Vantage INSIDER_TRANSACTIONS.

    Persists raw transactions under reports/.cache/web/alpha_vantage/<TICKER>/insider_transactions.json
    Returns {transactions, paths}.
    """
    if not api_key:
        raise RuntimeError(
            "Missing ALPHAVANTAGE_API_KEY. Set it in .env or environment."
        )
    try:
        import requests  # type: ignore
        import time
    except Exception as e:
        raise RuntimeError(
            "Missing dependency 'requests'. Install it (e.g., 'uv add requests')."
        ) from e

    base = "https://www.alphavantage.co/query"
    params = {
        "function": "INSIDER_TRANSACTIONS",
        "symbol": ticker.upper(),
        "apikey": api_key,
    }
    last_exc = None
    for attempt in range(5):
        try:
            r = requests.get(base, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and (data.get("Note") or data.get("Information")):
                last_exc = RuntimeError(data.get("Note") or data.get("Information"))
                time.sleep(2 + attempt)
                continue
            break
        except Exception as e:
            last_exc = e
            time.sleep(1.2 + attempt)
    else:
        raise RuntimeError(f"Alpha Vantage INSIDER_TRANSACTIONS failed: {last_exc}")

    tx = data.get("transactions") or data.get("data") or data.get("insiderTransactions") or []
    if not isinstance(tx, list):
        tx = []

    out_dir = out_root / ".cache" / "web" / "alpha_vantage" / ticker.upper()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "insider_transactions.json"
    path.write_text(json.dumps(tx, indent=2), encoding="utf-8")

    return {"transactions": tx, "paths": {"transactions": str(path)}}
