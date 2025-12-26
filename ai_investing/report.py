"""Plain text report generation (MVP).

Builds a conservative, evidence-based report and writes it to disk.
If an LLM memo is provided, it is included in the report; otherwise a
deterministic summary is used.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional


def _fmt_pct(x: Optional[float]) -> str:
    try:
        return f"{float(x)*100:.2f}%"
    except Exception:
        return "Not available"


def _fmt_ratio(x: Optional[float]) -> str:
    try:
        return f"{float(x):.2f}"
    except Exception:
        return "Not available"


def build_report_text(ctx: Dict[str, Any]) -> str:
    lines = []
    # Title
    title = f"# Value Investing Research Report — {ctx.get('ticker','UNKNOWN')}"
    lines.append(title)
    lines.append("")
    lines.append(f"- Date: {ctx.get('asof','')}")
    lines.append(f"- Company: {ctx.get('company_name','Not available')} (CIK {ctx.get('cik','')})")
    lines.append("")

    # Summary Verdict
    lines.append("## Summary Verdict (SEC)")
    lines.append(f"- Classification: **{ctx.get('sec_classification','?')}**")
    lines.append(f"- Confidence: **{ctx.get('sec_confidence','?')}**")
    lines.append("")

    # Business Overview
    lines.append("## Business Overview")
    overview = ctx.get("business_overview") or "Not available from SEC-only MVP."
    lines.append(overview)
    lines.append("")

    # Financial Highlights (SEC) with citations
    m = (ctx.get("sec_metrics") or {}).get("metrics", {})
    prov = (ctx.get("sec_metrics") or {}).get("provenance", {})
    rc = m.get("revenue_cagr", {})
    rc_prov = prov.get("revenue_cagr", {})
    gm = m.get("gross_margin", {})
    cov = m.get("interest_coverage_latest", {})
    lev = m.get("leverage_latest", {})
    fcf = m.get("fcf", {})
    fcf_prov = prov.get("fcf", {})

    lines.append("## Financial Highlights (SEC)")
    if rc.get("available"):
        sref = rc_prov.get("start", {})
        eref = rc_prov.get("end", {})
        lines.append(
            f"- Revenue CAGR: **{rc.get('cagr'):.4f}** over {rc.get('years')} years "
            f"(Start accn {sref.get('accn')}, End accn {eref.get('accn')})"
        )
    else:
        lines.append("- Revenue CAGR: Not available")
    lines.append(f"- Gross margin mean/std (pp): **{gm.get('mean_pp')}** / **{gm.get('std_pp')}**")
    lines.append(f"- Interest coverage (latest): **{cov.get('ratio')}**")
    lines.append(
        f"- Net debt/EBITDA (latest): **{lev.get('net_debt_to_ebitda')}**"
    )
    if fcf:
        lines.append(
            f"- FCF (latest): **{fcf.get('latest')}** (CFO accn {fcf_prov.get('cfo',{}).get('accn')}, CapEx accn {fcf_prov.get('capex',{}).get('accn')})"
        )
    lines.append("")

    # Insider Activity
    ins = ctx.get("insiders_summary") or {}
    lines.append("## Insider Activity (Alpha Vantage)")
    w12 = (ins.get("windows", {}) or {}).get("12m", {})
    lines.append(
        f"- 12m: net shares = **{w12.get('net_shares')}**, buyers = **{w12.get('unique_buyers')}**, sellers = **{w12.get('unique_sellers')}**"
    )
    lines.append(
        f"- Clustered buying events: **{len((ins.get('clustered_buying',{}) or {}).get('events', []))}**"
    )
    lines.append(
        f"- Routine sellers flagged: **{len((ins.get('routine_selling',{}) or {}).get('routine_sellers', {}))}**"
    )
    lines.append(f"- Owner alignment: **{ins.get('owner_alignment','Not assessed')}**")
    lines.append("")

    # SEC vs Alpha Vantage comparison (optional)
    if ctx.get("av_metrics"):
        avm = (ctx.get("av_metrics") or {}).get("metrics", {})
        lines.append("## SEC vs Alpha Vantage — Comparison")
        # Simple table for a few core metrics
        lines.append("")
        lines.append("| Metric | SEC | Alpha Vantage |")
        lines.append("|---|---:|---:|")
        # Revenue CAGR
        rc_sec = m.get("revenue_cagr", {})
        rc_av = (avm.get("revenue_cagr") or {}) if isinstance(avm.get("revenue_cagr"), dict) else {}
        def fmt_cagr(row):
            if not row or not row.get("available"):
                return "N/A"
            return f"{row.get('cagr'):.4f} ({row.get('years')}y)"
        lines.append(f"| Revenue CAGR | {fmt_cagr(rc_sec)} | {fmt_cagr(rc_av)} |")
        # Gross margin std
        gm_sec = gm.get("std_pp")
        gm_av = ((avm.get("gross_margin") or {}).get("std_pp") if isinstance(avm.get("gross_margin"), dict) else None)
        lines.append(f"| Gross margin std (pp) | {gm_sec} | {gm_av} |")
        # Interest coverage
        lines.append(f"| Interest coverage (latest) | {cov.get('ratio')} | {((avm.get('interest_coverage_latest') or {}).get('ratio') if isinstance(avm.get('interest_coverage_latest'), dict) else None)} |")
        # Net debt/EBITDA
        lines.append(f"| Net debt/EBITDA (latest) | {lev.get('net_debt_to_ebitda')} | {((avm.get('leverage_latest') or {}).get('net_debt_to_ebitda') if isinstance(avm.get('leverage_latest'), dict) else None)} |")
        lines.append("")

    # LLM memo
    lines.append("## Value-Investing Memo")
    memo = ctx.get("llm_memo")
    if memo:
        lines.append(memo)
    else:
        lines.append(
            "> Memo not generated (no API key or call failed). Proceed with SEC metrics and signals above."
        )
    lines.append("")

    # Risks & what would change my mind
    lines.append("## Key Risks and Failure Modes")
    rf = (ctx.get("sec_signals") or {}).get("red_flags", {})
    for k, v in rf.items():
        lines.append(f"- {k.replace('_',' ').title()}: {'Yes' if v else 'No' if v is not None else 'Unknown'}")
    lines.append("")

    lines.append("## What Would Change My Mind")
    lines.append("- Clear, sustained FCF generation if currently negative.")
    lines.append("- Demonstrated margin stability and recovery if recently volatile.")
    lines.append("- Deleveraging or improved interest coverage if currently weak.")
    lines.append("")

    # Sources and citations
    lines.append("## Sources and Citations")
    # SEC filings with links (if available)
    sel = ctx.get("sec_filings") or {}
    if sel:
        tenk = sel.get("10-K") or {}
        if tenk:
            lines.append(f"- 10-K ({tenk.get('filingDate')}), accn {tenk.get('accessionNumber')}: {tenk.get('indexUrl')}")
        tens = sel.get("10-Q") or []
        for q in tens:
            lines.append(f"- 10-Q ({q.get('filingDate')}), accn {q.get('accessionNumber')}: {q.get('indexUrl')}")
        def14a = sel.get("DEF 14A") or {}
        if def14a:
            lines.append(f"- DEF 14A ({def14a.get('filingDate')}), accn {def14a.get('accessionNumber')}: {def14a.get('indexUrl')}")
        # 8-K and 4 counts
        eightk = sel.get("8-K") or []
        if eightk:
            lines.append(f"- 8-K (last 90d): {len(eightk)} filings")
        f4 = sel.get("4") or []
        if f4:
            lines.append(f"- Form 4 (24m): {len(f4)} filings")
    # Files used
    for s in ctx.get("sources", []):
        lines.append(f"- {s}")
    lines.append("")

    return "\n".join(lines)


def write_report(output_path: Path, context: Dict[str, Any]) -> None:
    text = build_report_text(context)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
