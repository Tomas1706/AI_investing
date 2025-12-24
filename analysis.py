"""Rule-based signals and flags (MVP).

Consumes computed metrics and optional insider analysis to produce
explicit boolean/threshold-based signals and red flags.
"""

from __future__ import annotations

from math import isfinite
from typing import Dict, Any, Optional


def _gt(x: Optional[float], thr: float) -> Optional[bool]:
    try:
        return float(x) > thr
    except Exception:
        return None


def _ge(x: Optional[float], thr: float) -> Optional[bool]:
    try:
        return float(x) >= thr
    except Exception:
        return None


def _le(x: Optional[float], thr: float) -> Optional[bool]:
    try:
        return float(x) <= thr
    except Exception:
        return None


def build_signals(metrics: Dict[str, Any], insiders: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    m = metrics.get("metrics", {}) if "metrics" in metrics else metrics

    # Durability
    rc = m.get("revenue_cagr", {}) or {}
    rev_cagr = rc.get("cagr")
    revenue_growth_ok = _gt(rev_cagr, 0.0)
    rd = m.get("revenue_drawdowns", {}) or {}
    down_years = rd.get("down_years")
    max_decl = rd.get("max_single_year_decline_pp")
    revenue_stability_ok = None
    try:
        revenue_stability_ok = (down_years is not None and down_years <= 2) and (
            max_decl is not None and max_decl <= 15.0
        )
    except Exception:
        revenue_stability_ok = None

    # Moat/stability
    gm = m.get("gross_margin", {}) or {}
    gm_std = gm.get("std_pp")
    gm_drop_flag = gm.get("drop_gt_5pp")
    gross_margin_stable = None
    try:
        gross_margin_stable = (gm_std is not None and gm_std <= 4.0) and (gm_drop_flag is False)
    except Exception:
        gross_margin_stable = None
    op_persist = m.get("operating_margin_persistence", {}) or {}
    operating_margin_persistent = bool(op_persist.get("persistent")) if op_persist else None

    # Balance sheet
    cov = m.get("interest_coverage_latest", {}) or {}
    coverage_ok = _ge(cov.get("ratio"), 2.0)
    lev = m.get("leverage_latest", {}) or {}
    leverage_ok = _le(lev.get("net_debt_to_ebitda"), 4.0)
    cur = m.get("current_ratio_latest", {}) or {}
    liquidity_ok = _ge(cur.get("ratio"), 1.0)

    # Capital allocation & FCF
    fcf = m.get("fcf", {}) or {}
    fcf_years = fcf.get("years") or 0
    fcf_pos = fcf.get("positive_years") or 0
    fcf_consistent = None
    try:
        if fcf_years >= 3:
            fcf_consistent = fcf_pos >= (fcf_years - 1)
        elif fcf_years > 0:
            fcf_consistent = fcf_pos == fcf_years
        else:
            fcf_consistent = None
    except Exception:
        fcf_consistent = None
    shares = m.get("share_count_trend", {}) or {}
    dilution_pct = shares.get("pct_change")
    dilution_flag = None
    reduction_flag = None
    try:
        if dilution_pct is not None:
            dilution_flag = dilution_pct > 5.0
            reduction_flag = dilution_pct < -5.0
    except Exception:
        pass

    # Insider alignment (if available)
    insider_alignment = None
    clustered_events = None
    routine_sellers = None
    if insiders:
        insider_alignment = insiders.get("owner_alignment")
        clustered_events = len(insiders.get("clustered_buying", {}).get("events", []))
        routine_sellers = len(insiders.get("routine_selling", {}).get("routine_sellers", {}))

    # Red flags
    rf_negative_fcf_sustained = fcf_years >= 2 and fcf_pos == 0
    rf_leverage = leverage_ok is not None and leverage_ok is False
    rf_coverage = coverage_ok is not None and coverage_ok is False
    rf_revenue_declines = None
    try:
        rf_revenue_declines = (down_years or 0) >= 2 and (max_decl or 0.0) > 15.0
    except Exception:
        rf_revenue_declines = None

    signals = {
        "durability": {
            "revenue_growth_ok": revenue_growth_ok,
            "revenue_stability_ok": revenue_stability_ok,
        },
        "moat": {
            "gross_margin_stable": gross_margin_stable,
            "operating_margin_persistent": operating_margin_persistent,
        },
        "balance_sheet": {
            "leverage_ok": leverage_ok,
            "coverage_ok": coverage_ok,
            "liquidity_ok": liquidity_ok,
        },
        "capital_allocation": {
            "fcf_consistent": fcf_consistent,
            "dilution_flag": dilution_flag,
            "reduction_flag": reduction_flag,
        },
        "insiders": {
            "alignment": insider_alignment,
            "clustered_buying_events": clustered_events,
            "routine_sellers": routine_sellers,
        },
        "red_flags": {
            "negative_fcf_sustained": rf_negative_fcf_sustained,
            "high_leverage": rf_leverage,
            "weak_coverage": rf_coverage,
            "revenue_declines": rf_revenue_declines,
        },
    }
    return signals

