"""Deterministic metric computations for the MVP.

Consumes the series produced by sec.extract_xbrl_timeseries and returns
auditable, rule-based metrics with provenance references.
"""

from __future__ import annotations

from typing import Dict, Any, List, Tuple, Optional


def _annual_series(rows: List[Dict[str, Any]], prefer_form: str = "10-K") -> Dict[int, Dict[str, Any]]:
    """Reduce a raw series to annual (FY) datapoints keyed by fiscal year.
    Preference order:
    1) rows where fp == 'FY'
    2) among those, prefer specified form (e.g., 10-K)
    3) else, fall back to latest filed in that FY
    If no 'fy' present, derive year from 'end' (YYYY-MM-DD).
    """
    by_year: Dict[int, List[Dict[str, Any]]] = {}
    for r in rows or []:
        fy = r.get("fy")
        if isinstance(fy, int):
            year = fy
        else:
            # derive from end date
            end = (r.get("end") or "")[:4]
            try:
                year = int(end)
            except Exception:
                continue
        by_year.setdefault(year, []).append(r)

    annual: Dict[int, Dict[str, Any]] = {}
    for year, rs in by_year.items():
        # Prefer FY entries
        fy_rows = [x for x in rs if (x.get("fp") or "").upper() == "FY"] or rs
        # Prefer chosen form
        prefer_rows = [x for x in fy_rows if (x.get("form") or "").upper() == prefer_form]
        candidates = prefer_rows or fy_rows
        # Choose latest filed
        candidates.sort(key=lambda x: x.get("filed") or "", reverse=True)
        annual[year] = candidates[0]
    return annual


def _cagr(start_val: float, end_val: float, years: int) -> Optional[float]:
    if start_val is None or end_val is None or years <= 0:
        return None
    if start_val <= 0 or end_val <= 0:
        return None
    try:
        return (end_val / start_val) ** (1.0 / years) - 1.0
    except Exception:
        return None


def _choose_cagr_window(year_vals: List[Tuple[int, float]]) -> Dict[str, Any]:
    """Choose the longest available window, pref: 10y -> 7y -> 5y.
    Returns dict with value, years, start_year, end_year, start_val, end_val.
    """
    if not year_vals:
        return {"available": False}
    year_vals.sort(key=lambda x: x[0])
    years_list = [10, 7, 5]
    for target in years_list:
        # Need span >= target-1 (e.g., 10y window requires end_year - start_year >= 9)
        for i in range(len(year_vals)):
            for j in range(i + 1, len(year_vals)):
                start_y, start_v = year_vals[i]
                end_y, end_v = year_vals[j]
                span = end_y - start_y
                if span >= (target - 1):
                    val = _cagr(start_v, end_v, span)
                    if val is not None:
                        return {
                            "available": True,
                            "cagr": val,
                            "years": span,
                            "start_year": start_y,
                            "end_year": end_y,
                            "start_val": start_v,
                            "end_val": end_v,
                        }
    # If nothing matched, try any available span >= 2
    best = None
    for i in range(len(year_vals)):
        for j in range(i + 1, len(year_vals)):
            start_y, start_v = year_vals[i]
            end_y, end_v = year_vals[j]
            span = end_y - start_y
            if span >= 2:
                val = _cagr(start_v, end_v, span)
                if val is not None:
                    best = {
                        "available": True,
                        "cagr": val,
                        "years": span,
                        "start_year": start_y,
                        "end_year": end_y,
                        "start_val": start_v,
                        "end_val": end_v,
                    }
    return best or {"available": False}


def _std(values: List[float]) -> Optional[float]:
    n = len(values)
    if n == 0:
        return None
    mean = sum(values) / n
    var = sum((x - mean) ** 2 for x in values) / n
    return var ** 0.5


def compute_metrics(series: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    prov: Dict[str, Any] = {}

    # Annualized essential series
    revenue_annual = _annual_series(series.get("revenue", []))
    gp_annual = _annual_series(series.get("gross_profit", []))
    opinc_annual = _annual_series(series.get("operating_income", []))
    netinc_annual = _annual_series(series.get("net_income", []))
    shares_annual = _annual_series(series.get("diluted_shares", []), prefer_form="10-K")
    cfo_annual = _annual_series(series.get("cfo", []))
    capex_annual = _annual_series(series.get("capex", []))
    interest_annual = _annual_series(series.get("interest_expense", []))
    da_annual = _annual_series(series.get("depreciation_amortization", []))
    assets_cur_annual = _annual_series(series.get("assets_current", []))
    liab_cur_annual = _annual_series(series.get("liabilities_current", []))
    cash_annual = _annual_series(series.get("cash", []))
    rcash_annual = _annual_series(series.get("restricted_cash", []))
    debt_total_annual = _annual_series(series.get("total_debt", []))

    # Revenue CAGR window
    rev_year_vals = [
        (y, float(r.get("val")))
        for y, r in revenue_annual.items()
        if r.get("val") is not None
    ]
    rev_window = _choose_cagr_window(rev_year_vals)
    metrics["revenue_cagr"] = rev_window
    if rev_window and rev_window.get("available"):
        # provenance: start and end filing references
        sy = rev_window["start_year"]
        ey = rev_window["end_year"]
        sref = revenue_annual.get(sy, {})
        eref = revenue_annual.get(ey, {})
        prov["revenue_cagr"] = {
            "start": {k: sref.get(k) for k in ("form", "accn", "filed", "end")},
            "end": {k: eref.get(k) for k in ("form", "accn", "filed", "end")},
        }
    else:
        prov["revenue_cagr"] = {}

    # Revenue drawdowns and down-year count
    years_sorted = sorted(revenue_annual.keys())
    down_years = 0
    max_decline_pp = 0.0
    for i in range(1, len(years_sorted)):
        y0, y1 = years_sorted[i - 1], years_sorted[i]
        v0 = revenue_annual[y0].get("val")
        v1 = revenue_annual[y1].get("val")
        try:
            if v0 and v1 and v1 < v0:
                down_years += 1
                decline = (v0 - v1) / v0 * 100.0
                if decline > max_decline_pp:
                    max_decline_pp = decline
        except Exception:
            pass
    metrics["revenue_drawdowns"] = {
        "down_years": down_years,
        "max_single_year_decline_pp": max_decline_pp,
    }

    # Gross margin level and stability
    gm_series: List[Tuple[int, float]] = []
    for y in sorted(set(revenue_annual.keys()) & set(gp_annual.keys())):
        r = revenue_annual[y].get("val")
        g = gp_annual[y].get("val")
        if r and g:
            try:
                gm_series.append((y, float(g) / float(r)))
            except Exception:
                pass
    gm_values = [x[1] * 100.0 for x in gm_series]
    gm_mean = sum(gm_values) / len(gm_values) if gm_values else None
    gm_std = _std(gm_values) if gm_values else None
    # Single-year drop >5pp flag
    gm_drop_flag = False
    for i in range(1, len(gm_series)):
        prev = gm_series[i - 1][1] * 100.0
        cur = gm_series[i][1] * 100.0
        try:
            if prev - cur > 5.0:
                gm_drop_flag = True
                break
        except Exception:
            pass
    metrics["gross_margin"] = {
        "mean_pp": gm_mean,
        "std_pp": gm_std,
        "years": len(gm_series),
        "drop_gt_5pp": gm_drop_flag,
    }

    # Operating margin persistence
    om_series: List[Tuple[int, float]] = []
    for y in sorted(set(revenue_annual.keys()) & set(opinc_annual.keys())):
        r = revenue_annual[y].get("val")
        o = opinc_annual[y].get("val")
        if r and o is not None and r != 0:
            try:
                om_series.append((y, float(o) / float(r)))
            except Exception:
                pass
    om_pos_years = sum(1 for _, v in om_series if v > 0)
    om_persist = (om_pos_years / len(om_series)) >= 0.8 if om_series else False
    metrics["operating_margin_persistence"] = {
        "years": len(om_series),
        "positive_years": om_pos_years,
        "persistent": om_persist,
    }

    # FCF and consistency
    fcf_series: List[Tuple[int, float]] = []
    for y in sorted(set(cfo_annual.keys()) | set(capex_annual.keys())):
        cfo = (cfo_annual.get(y) or {}).get("val")
        cap = (capex_annual.get(y) or {}).get("val")
        if cfo is None or cap is None:
            continue
        try:
            fcf_series.append((y, float(cfo) - float(cap)))
        except Exception:
            pass
    fcf_pos_years = sum(1 for _, v in fcf_series if v > 0)
    metrics["fcf"] = {
        "years": len(fcf_series),
        "positive_years": fcf_pos_years,
        "latest": fcf_series[-1][1] if fcf_series else None,
    }
    # Provenance example: latest year references
    if fcf_series:
        ly = fcf_series[-1][0]
        prov["fcf"] = {
            "cfo": {k: (cfo_annual.get(ly) or {}).get(k) for k in ("form", "accn", "filed")},
            "capex": {k: (capex_annual.get(ly) or {}).get(k) for k in ("form", "accn", "filed")},
        }
    else:
        prov["fcf"] = {}

    # Interest coverage (latest)
    coverage_latest = None
    cov_year = None
    for y in sorted(set(opinc_annual.keys()) & set(interest_annual.keys())):
        ebit = opinc_annual[y].get("val")
        intr = interest_annual[y].get("val")
        try:
            if ebit is not None and intr and float(intr) > 0:
                cov = float(ebit) / float(intr)
                coverage_latest = cov
                cov_year = y
        except Exception:
            pass
    metrics["interest_coverage_latest"] = {
        "year": cov_year,
        "ratio": coverage_latest,
    }

    # Liquidity: current ratio (latest)
    cur_ratio = None
    cur_year = None
    for y in sorted(set(assets_cur_annual.keys()) & set(liab_cur_annual.keys())):
        a = assets_cur_annual[y].get("val")
        l = liab_cur_annual[y].get("val")
        try:
            if a is not None and l and float(l) != 0:
                cur_ratio = float(a) / float(l)
                cur_year = y
        except Exception:
            pass
    metrics["current_ratio_latest"] = {"year": cur_year, "ratio": cur_ratio}

    # Leverage: net debt and Net Debt/EBITDA (latest)
    nd_year = None
    net_debt_excl_rc = None
    net_debt_incl_rc = None
    for y in sorted(set(debt_total_annual.keys()) | set(cash_annual.keys()) | set(rcash_annual.keys())):
        total_debt = (debt_total_annual.get(y) or {}).get("val")
        cash = (cash_annual.get(y) or {}).get("val") or 0.0
        rcash = (rcash_annual.get(y) or {}).get("val") or 0.0
        try:
            if total_debt is not None:
                net_debt_excl_rc = float(total_debt) - float(cash)
                net_debt_incl_rc = float(total_debt) - (float(cash) + float(rcash))
                nd_year = y
        except Exception:
            pass
    # EBITDA approximation (latest)
    ebitda_latest = None
    ebitda_year = None
    for y in sorted(set(opinc_annual.keys()) & set(da_annual.keys())):
        ebit = opinc_annual[y].get("val")
        da = da_annual[y].get("val")
        try:
            if ebit is not None and da is not None:
                ebitda_latest = float(ebit) + float(da)
                ebitda_year = y
        except Exception:
            pass
    nd_ebitda = None
    if nd_year is not None and ebitda_latest and ebitda_latest > 0:
        try:
            nd_ebitda = float(net_debt_excl_rc) / float(ebitda_latest) if net_debt_excl_rc is not None else None
        except Exception:
            nd_ebitda = None
    metrics["leverage_latest"] = {
        "year": nd_year,
        "net_debt_excl_restricted": net_debt_excl_rc,
        "net_debt_incl_restricted": net_debt_incl_rc,
        "ebitda_year": ebitda_year,
        "ebitda_approx": ebitda_latest,
        "net_debt_to_ebitda": nd_ebitda,
    }

    # Share count trend (dilution vs reduction)
    shares_vals = sorted(
        [(y, float(r.get("val"))) for y, r in shares_annual.items() if r.get("val") is not None],
        key=lambda x: x[0],
    )
    shares_trend = {}
    if len(shares_vals) >= 2:
        s0y, s0 = shares_vals[0]
        s1y, s1 = shares_vals[-1]
        try:
            pct = (s1 - s0) / s0 * 100.0 if s0 != 0 else None
        except Exception:
            pct = None
        shares_trend = {
            "start_year": s0y,
            "end_year": s1y,
            "start": s0,
            "end": s1,
            "pct_change": pct,
            "direction": "reduction" if (pct is not None and pct < 0) else "dilution" if (pct is not None and pct > 0) else "flat",
        }
    metrics["share_count_trend"] = shares_trend

    return {"metrics": metrics, "provenance": prov}
