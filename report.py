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
    title = f"Value Investing Research Report — {ctx.get('ticker','UNKNOWN')}"
    lines.append(title)
    lines.append("".ljust(len(title), "="))
    lines.append("")
    lines.append(f"Date: {ctx.get('asof','')}")
    lines.append(f"Company: {ctx.get('company_name','Not available')} (CIK {ctx.get('cik','')})")
    lines.append("")

    # Business overview (placeholder)
    lines.append("Business Overview")
    lines.append("-" * 18)
    overview = ctx.get("business_overview") or "Not available from SEC-only MVP."
    lines.append(overview)
    lines.append("")

    # Metrics highlights (SEC)
    m = (ctx.get("sec_metrics") or {}).get("metrics", {})
    rc = m.get("revenue_cagr", {})
    gm = m.get("gross_margin", {})
    cov = m.get("interest_coverage_latest", {})
    lev = m.get("leverage_latest", {})
    lines.append("Financial Highlights (SEC)")
    lines.append("-" * 24)
    if rc.get("available"):
        lines.append(f"- Revenue CAGR: {rc.get('cagr'):.4f} over {rc.get('years')} years")
    else:
        lines.append("- Revenue CAGR: Not available")
    lines.append(f"- Gross margin mean/std (pp): {gm.get('mean_pp')} / {gm.get('std_pp')}")
    lines.append(f"- Interest coverage (latest): {cov.get('ratio')}")
    lines.append(f"- Net debt/EBITDA (latest): {lev.get('net_debt_to_ebitda')}")
    lines.append("")

    # Insiders
    ins = ctx.get("insiders_summary") or {}
    lines.append("Insider Activity (Alpha Vantage)")
    lines.append("-" * 28)
    w12 = (ins.get("windows", {}) or {}).get("12m", {})
    lines.append(
        f"- 12m: net shares = {w12.get('net_shares')}, buyers = {w12.get('unique_buyers')}, sellers = {w12.get('unique_sellers')}"
    )
    lines.append(
        f"- Clustered buying events: {len((ins.get('clustered_buying',{}) or {}).get('events', []))}"
    )
    lines.append(
        f"- Routine sellers flagged: {len((ins.get('routine_selling',{}) or {}).get('routine_sellers', {}))}"
    )
    lines.append(f"- Owner alignment: {ins.get('owner_alignment','Not assessed')}")
    lines.append("")

    # Classification
    lines.append("Long-Term Verdict (SEC)")
    lines.append("-" * 21)
    lines.append(
        f"- Classification: {ctx.get('sec_classification','?')} (confidence: {ctx.get('sec_confidence','?')})"
    )
    lines.append("")

    # SEC vs Alpha Vantage comparison (optional)
    if ctx.get("av_metrics"):
        avm = (ctx.get("av_metrics") or {}).get("metrics", {})
        lines.append("SEC vs Alpha Vantage — Comparison")
        lines.append("-" * 33)
        lines.append(
            f"- Net debt/EBITDA: SEC {lev.get('net_debt_to_ebitda')} | AV {(avm.get('leverage_latest') or {}).get('net_debt_to_ebitda') if isinstance(avm.get('leverage_latest'), dict) else 'n/a'}"
        )
        # Keep comparison light; detailed diff can be added later
        lines.append("")

    # LLM memo
    memo = ctx.get("llm_memo")
    lines.append("Value-Investing Memo")
    lines.append("-" * 22)
    if memo:
        lines.append(memo)
    else:
        lines.append(
            "Memo not generated (no API key or call failed). Proceed with SEC metrics and signals above."
        )
    lines.append("")

    # Risks & what would change my mind — brief stubs informed by signals
    lines.append("Key Risks and Failure Modes")
    lines.append("-" * 27)
    rf = (ctx.get("sec_signals") or {}).get("red_flags", {})
    for k, v in rf.items():
        lines.append(f"- {k.replace('_',' ').title()}: {'Yes' if v else 'No' if v is not None else 'Unknown'}")
    lines.append("")

    lines.append("What Would Change My Mind")
    lines.append("-" * 25)
    lines.append("- Clear, sustained FCF generation if currently negative.")
    lines.append("- Demonstrated margin stability and recovery if recently volatile.")
    lines.append("- Deleveraging or improved interest coverage if currently weak.")
    lines.append("")

    # Sources and citations
    lines.append("Sources and Citations")
    lines.append("-" * 20)
    for s in ctx.get("sources", []):
        lines.append(f"- {s}")
    lines.append("")

    return "\n".join(lines)


def write_report(output_path: Path, context: Dict[str, Any]) -> None:
    text = build_report_text(context)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")

