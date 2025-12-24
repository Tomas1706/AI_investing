#!/usr/bin/env python3
import argparse
from datetime import datetime
from pathlib import Path

from config import load_config
from sec import fetch_filings, extract_xbrl_timeseries
from metrics import compute_metrics
from insiders import analyze_insiders
from analysis import build_signals
from scoring import classify


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="One-shot value investing research report generator (MVP, SEC-only)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--ticker", help="US stock ticker symbol (e.g., AAPL)")
    p.add_argument("--cik", help="Override CIK (bypasses ticker lookup)")
    p.add_argument("--out", help="Output directory root")
    p.add_argument("--asof", help="As-of date YYYY-MM-DD (filters filings up to this date)")
    p.add_argument("--no-web", action="store_true", help="Disable web context (later phase)")
    p.add_argument("--alpha-vantage", action="store_true", help="Also fetch fundamental data via Alpha Vantage (requires API key)")
    p.add_argument("--llm", action="store_true", help="Use OpenAI to generate a memo section if OPENAI_API_KEY is set")
    p.add_argument(
        "--verbose", "-v", action="count", default=0, help="Increase verbosity"
    )
    return p


def main() -> int:
    cfg = load_config()
    parser = build_parser()
    args = parser.parse_args()

    # Resolve output directory
    out_root = Path(args.out).resolve() if args.out else cfg.output_dir
    try:
        out_root.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[run] Warning: failed to create output dir '{out_root}': {e}")
        out_root = cfg.output_dir

    # Parse as-of date if provided
    asof_date = None
    if args.asof:
        try:
            asof_date = datetime.strptime(args.asof, "%Y-%m-%d").date()
        except ValueError:
            print("[run] Error: --asof must be YYYY-MM-DD")
            return 2

    # For now, Step 2 (ticker->CIK) is skipped; require --cik for Step 3
    if not args.ticker and not args.cik:
        print("[run] Error: --ticker or --cik is required")
        parser.print_help()
        return 2

    print("[run] Configuration loaded:")
    print(f"  APP_ENV: {cfg.app_env}")
    print(f"  OUTPUT_DIR: {out_root}")
    print(f"  SEC_USER_AGENT: {cfg.sec_user_agent}")
    print("[run] Arguments:")
    print(f"  ticker: {args.ticker}")
    print(f"  cik: {args.cik}")
    print(f"  asof: {asof_date}")
    print(f"  no_web: {args.no_web}")

    # Proceed to Step 3 (SEC filings retrieval) when CIK is provided
    if args.cik or cfg.override_cik:
        cik = (args.cik or cfg.override_cik).strip()
        print(f"[run] Step 3: Fetching SEC filings for CIK {cik} ...")
        try:
            result = fetch_filings(
                cik=cik,
                out_root=out_root,
                user_agent=cfg.sec_user_agent,
                form4_lookback_months=24,
                recent_q_count=3,
            )
        except Exception as e:
            print(f"[run] Error during filings retrieval: {e}")
            return 1

        # Basic summary
        sel = result.get("selected", {})
        print("[run] Retrieved filings summary:")
        print(f"  10-K latest: {sel.get('10-K', {}).get('filingDate')}")
        print(
            f"  10-Q count (latest {len(sel.get('10-Q', []))}): "
            + ", ".join([f.get('filingDate') for f in sel.get('10-Q', [])])
        )
        print(
            f"  8-K in last 90d: {len(sel.get('8-K', []))}"
        )
        print(f"  DEF 14A latest: {sel.get('DEF 14A', {}).get('filingDate')}")
        print(f"  Form 4 (24m) count: {len(sel.get('4', []))}")
        print(f"[run] Metadata cached at: {result.get('cache_paths', {}).get('metadata')}")
        print("[run] Step 3 complete.")

        # Step 4: Structured SEC financial data extraction (XBRL)
        print(f"[run] Step 4: Extracting XBRL timeseries for CIK {cik} ...")
        try:
            xbrl = extract_xbrl_timeseries(
                cik=cik,
                out_root=out_root,
                user_agent=cfg.sec_user_agent,
            )
        except Exception as e:
            print(f"[run] Error during XBRL extraction: {e}")
            return 1

        series = xbrl.get("series", {})
        print("[run] Extracted series counts:")
        for key in [
            "revenue",
            "cost_of_revenue",
            "gross_profit",
            "operating_income",
            "net_income",
            "diluted_shares",
            "cfo",
            "capex",
            "cash",
            "total_debt",
            "assets_current",
            "liabilities_current",
            "interest_expense",
            "depreciation_amortization",
        ]:
            cnt = len(series.get(key, []))
            print(f"  {key}: {cnt}")
        print(f"[run] Timeseries saved at: {xbrl.get('paths', {}).get('timeseries')}")
        print("[run] Step 4 complete.")

        # Step 5: Deterministic metric computation (no LLM)
        print("[run] Step 5: Computing value-oriented metrics ...")
        try:
            m = compute_metrics(series)
        except Exception as e:
            print(f"[run] Error during metric computation: {e}")
            return 1

        # Persist metrics to cache
        import json
        import os
        cik10_path = xbrl.get("paths", {}).get("facts", "").split("/")
        # facts path is .../.cache/sec/CIK##########/companyfacts.json
        # derive directory
        if cik10_path:
            cache_dir = Path("/").joinpath(*cik10_path[:-1]) if os.name != "nt" else Path("").joinpath(*cik10_path[:-1])
        else:
            cache_dir = out_root / ".cache" / "sec"
        metrics_path = Path(cache_dir) / "metrics.json"
        try:
            metrics_path.write_text(json.dumps(m, indent=2), encoding="utf-8")
            print(f"[run] Metrics saved at: {metrics_path}")
        except Exception as e:
            print(f"[run] Warning: failed to save metrics: {e}")

        # Print key highlights
        rc = m.get("metrics", {}).get("revenue_cagr", {})
        gm = m.get("metrics", {}).get("gross_margin", {})
        cov = m.get("metrics", {}).get("interest_coverage_latest", {})
        lev = m.get("metrics", {}).get("leverage_latest", {})
        print("[run] Metric highlights:")
        print(
            f"  Revenue CAGR: {rc.get('cagr')} over {rc.get('years')} years (start {rc.get('start_year')} → {rc.get('end_year')})"
        )
        print(
            f"  Gross margin mean/std (pp): {gm.get('mean_pp')} / {gm.get('std_pp')} (drop>5pp: {gm.get('drop_gt_5pp')})"
        )
        print(
            f"  Interest coverage latest ({cov.get('year')}): {cov.get('ratio')}"
        )
        print(
            f"  Net debt/EBITDA latest ({lev.get('year')}): {lev.get('net_debt_to_ebitda')}"
        )
        # Debug: show components for EBITDA approximation (latest FY)
        try:
            # Find latest overlapping FY for operating income and D&A
            op = xbrl.get("series", {}).get("operating_income", [])
            da = xbrl.get("series", {}).get("depreciation_amortization", [])
            def _annual_map(rows):
                mp = {}
                for r in rows:
                    fy = r.get("fy")
                    if isinstance(fy, int):
                        year = fy
                    else:
                        end = (r.get("end") or "")[:4]
                        try:
                            year = int(end)
                        except Exception:
                            continue
                    # prefer FY, then latest filed
                    bucket = mp.setdefault(year, [])
                    bucket.append(r)
                ann = {}
                for y, rows in mp.items():
                    fyrows = [x for x in rows if (x.get("fp") or "").upper() == "FY"] or rows
                    fyrows.sort(key=lambda x: x.get("filed") or "", reverse=True)
                    ann[y] = fyrows[0]
                return ann
            op_a = _annual_map(op)
            da_a = _annual_map(da)
            overlap_years = sorted(set(op_a.keys()) & set(da_a.keys()))
            if overlap_years:
                y = overlap_years[-1]
                opy, day = op_a[y], da_a[y]
                opv, dav = opy.get("val"), day.get("val")
                print("[debug] EBITDA components (latest FY):")
                print(
                    f"  Year {y} OperatingIncomeLoss: {opv} (form {opy.get('form')}, accn {opy.get('accn')}, filed {opy.get('filed')})"
                )
                print(
                    f"  Year {y} Depreciation&Amortization: {dav} (form {day.get('form')}, accn {day.get('accn')}, filed {day.get('filed')}, tag {day.get('tag')}, unit {day.get('unit')})"
                )
                try:
                    approx = float(opv) + float(dav)
                    print(f"  EBITDA approx (computed): {approx}")
                except Exception:
                    pass
        except Exception:
            pass
        print("[run] Step 5 complete.")

        # Step 7: Build signals and classify (SEC path)
        try:
            print("[run] Step 7: Building signals and classification (SEC) ...")
            sec_insiders = None  # SEC-native parsing not implemented; may use AV below
            sec_signals = build_signals(m, insiders=sec_insiders)
            sec_class, sec_conf = classify(sec_signals)
            # Persist
            import json
            cik10_dir = Path(xbrl.get("paths", {}).get("facts", "")).parent if xbrl.get("paths", {}).get("facts") else (out_root/".cache"/"sec")
            (cik10_dir / "signals.json").write_text(json.dumps(sec_signals, indent=2), encoding="utf-8")
            (cik10_dir / "classification.json").write_text(json.dumps({"classification": sec_class, "confidence": sec_conf}, indent=2), encoding="utf-8")
            print(f"[run] SEC classification: {sec_class} (confidence: {sec_conf})")
        except Exception as e:
            print(f"[run] Warning: failed to build SEC signals/classification: {e}")

        # Optional: Alpha Vantage fundamental series and metrics (similar to SEC pipeline)
        if args.alpha_vantage and args.ticker:
            print("[run] Alpha Vantage: fetching fundamental timeseries ...")
            try:
                from web import fetch_alpha_vantage_series, fetch_alpha_vantage_insider_transactions

                a = fetch_alpha_vantage_series(
                    ticker=args.ticker.upper(),
                    api_key=cfg.alpha_vantage_api_key or "",
                    out_root=out_root,
                )
                av_series = a.get("series", {})
                print("[run] Alpha Vantage series counts:")
                for key in [
                    "revenue",
                    "cost_of_revenue",
                    "gross_profit",
                    "operating_income",
                    "net_income",
                    "diluted_shares",
                    "cfo",
                    "capex",
                    "cash",
                    "total_debt",
                    "assets_current",
                    "liabilities_current",
                    "interest_expense",
                    "depreciation_amortization",
                ]:
                    print(f"  {key}: {len(av_series.get(key, []))}")

                # Compute comparable metrics on AV series
                avm = compute_metrics(av_series)
                # Persist AV metrics alongside timeseries
                import json as _json
                av_out_dir = out_root / ".cache" / "web" / "alpha_vantage" / args.ticker.upper()
                av_out_dir.mkdir(parents=True, exist_ok=True)
                av_metrics_path = av_out_dir / "metrics.json"
                try:
                    av_metrics_path.write_text(_json.dumps(avm, indent=2), encoding="utf-8")
                    print(f"[run] Alpha Vantage metrics saved at: {av_metrics_path}")
                except Exception as e:
                    print(f"[run] Warning: failed to save AV metrics: {e}")
                print("[run] Alpha Vantage metric highlights:")
                rc = avm.get("metrics", {}).get("revenue_cagr", {})
                gm = avm.get("metrics", {}).get("gross_margin", {})
                cov = avm.get("metrics", {}).get("interest_coverage_latest", {})
                lev = avm.get("metrics", {}).get("leverage_latest", {})
                print(
                    f"  Revenue CAGR: {rc.get('cagr')} over {rc.get('years')} years (start {rc.get('start_year')} → {rc.get('end_year')})"
                )
                print(
                    f"  Gross margin mean/std (pp): {gm.get('mean_pp')} / {gm.get('std_pp')} (drop>5pp: {gm.get('drop_gt_5pp')})"
                )
                print(
                    f"  Interest coverage latest ({cov.get('year')}): {cov.get('ratio')}"
                )
                print(
                    f"  Net debt/EBITDA latest ({lev.get('year')}): {lev.get('net_debt_to_ebitda')}"
                )
                print(f"[run] Alpha Vantage timeseries at: {a.get('paths',{}).get('timeseries')}")
                # Build AV signals/classification (optional)
                try:
                    av_signals = build_signals(avm)
                    av_class, av_conf = classify(av_signals)
                    av_signals_path = av_out_dir / "signals.json"
                    av_class_path = av_out_dir / "classification.json"
                    av_signals_path.write_text(_json.dumps(av_signals, indent=2), encoding="utf-8")
                    av_class_path.write_text(_json.dumps({"classification": av_class, "confidence": av_conf}, indent=2), encoding="utf-8")
                    print(f"[run] Alpha Vantage classification: {av_class} (confidence: {av_conf})")
                except Exception as e:
                    print(f"[run] Warning: failed to build AV signals/classification: {e}")
            except Exception as e:
                print(f"[run] Alpha Vantage fetch skipped/error: {e}")

            # Step 6: Insider activity analysis via Alpha Vantage
            try:
                print("[run] Step 6: Insider activity (Alpha Vantage) ...")
                av_tx = fetch_alpha_vantage_insider_transactions(
                    ticker=args.ticker.upper(),
                    api_key=cfg.alpha_vantage_api_key or "",
                    out_root=out_root,
                )
                tx = av_tx.get("transactions", [])
                # Try to pass shares_outstanding from AV overview metrics if available
                # (We didn't fetch overview here; skip and compute dollars-based cluster)
                ins_summary = analyze_insiders(transactions=tx)
                # Persist
                import json as _json
                av_out_dir = out_root / ".cache" / "web" / "alpha_vantage" / args.ticker.upper()
                av_ins_path = av_out_dir / "insiders_summary.json"
                av_ins_path.write_text(_json.dumps(ins_summary, indent=2), encoding="utf-8")
                # Print summary
                w = ins_summary.get("windows", {})
                print("[run] Insider 12m: net shares =", w.get("12m", {}).get("net_shares"),
                      ", buyers =", w.get("12m", {}).get("unique_buyers"),
                      ", sellers =", w.get("12m", {}).get("unique_sellers"))
                print("[run] Clustered buying events:", len(ins_summary.get("clustered_buying", {}).get("events", [])))
                print("[run] Routine sellers flagged:", len(ins_summary.get("routine_selling", {}).get("routine_sellers", {})))
                print(f"[run] Insider summary saved at: {av_ins_path}")
            except Exception as e:
                print(f"[run] Insider analysis skipped/error: {e}")

        # SEC vs Alpha Vantage comparison summary (if AV ran)
        try:
            if args.alpha_vantage and args.ticker:
                print("[run] SEC vs Alpha Vantage comparison (computed metrics):")
                # SEC metrics already in m; AV metrics are avm above if fetch succeeded
                # avm might be out of scope if AV failed; guard
                if 'avm' in locals():
                    def _fmt_cagr(x):
                        if not x or not x.get('available'):
                            return 'N/A'
                        return f"{x.get('cagr'):.4f} over {x.get('years')}y"
                    print("  Revenue CAGR: SEC", _fmt_cagr(m.get('metrics', {}).get('revenue_cagr')), "| AV", _fmt_cagr(avm.get('metrics', {}).get('revenue_cagr')))
                    sec_gm = m.get('metrics', {}).get('gross_margin', {})
                    av_gm = avm.get('metrics', {}).get('gross_margin', {})
                    print(f"  Gross margin mean/std (pp): SEC {sec_gm.get('mean_pp')} / {sec_gm.get('std_pp')} | AV {av_gm.get('mean_pp')} / {av_gm.get('std_pp')}")
                    sec_cov = m.get('metrics', {}).get('interest_coverage_latest', {})
                    av_cov = avm.get('metrics', {}).get('interest_coverage_latest', {})
                    print(f"  Interest coverage: SEC {sec_cov.get('ratio')} | AV {av_cov.get('ratio')}")
                    sec_lev = m.get('metrics', {}).get('leverage_latest', {})
                    av_lev = avm.get('metrics', {}).get('leverage_latest', {})
                    print(f"  Net debt/EBITDA: SEC {sec_lev.get('net_debt_to_ebitda')} | AV {av_lev.get('net_debt_to_ebitda')}")
                    # Classification comparison
                    if 'av_signals' in locals():
                        print(f"  Classification: SEC {sec_class} ({sec_conf}) | AV {av_class} ({av_conf})")
                else:
                    print("  (Alpha Vantage metrics unavailable; comparison skipped)")
        except Exception:
            pass
        # Step 8: Report generation
        if args.ticker:
            print("[run] Step 8: Generating report ...")
            from report import write_report
            from llm import generate_memo

            asof_out = asof_date.isoformat() if asof_date else datetime.utcnow().date().isoformat()
            out_file = out_root / args.ticker.upper() / f"{args.ticker.upper()}_{asof_out}.txt"

            # Build evidence bundle for LLM
            evidence = {
                "ticker": args.ticker.upper(),
                "cik": cik,
                "asof": asof_out,
                "sec_metrics": m,
                "sec_signals": sec_signals if 'sec_signals' in locals() else None,
                "sec_classification": sec_class if 'sec_class' in locals() else None,
                "sec_confidence": sec_conf if 'sec_conf' in locals() else None,
                "alpha_vantage_metrics": avm if 'avm' in locals() else None,
                "insiders_summary": ins_summary if 'ins_summary' in locals() else None,
            }

            memo_text = None
            if args.llm and cfg.openai_api_key:
                try:
                    memo_text = generate_memo(
                        evidence=evidence,
                        api_key=cfg.openai_api_key,
                        model=cfg.openai_model,
                        temperature=0.2,
                    )
                except Exception as e:
                    print(f"[run] LLM memo generation failed: {e}")

            sources = [
                xbrl.get('paths', {}).get('facts'),
                xbrl.get('paths', {}).get('timeseries'),
                result.get('cache_paths', {}).get('metadata'),
            ]
            if args.alpha_vantage:
                sources += [
                    (out_root / '.cache' / 'web' / 'alpha_vantage' / args.ticker.upper() / 'timeseries.json').as_posix(),
                    (out_root / '.cache' / 'web' / 'alpha_vantage' / args.ticker.upper() / 'insider_transactions.json').as_posix(),
                ]

            write_report(
                output_path=out_file,
                context={
                    "ticker": args.ticker.upper(),
                    "cik": cik,
                    "asof": asof_out,
                    "company_name": result.get('companyName'),
                    "sec_metrics": m,
                    "sec_signals": sec_signals if 'sec_signals' in locals() else None,
                    "sec_classification": sec_class if 'sec_class' in locals() else None,
                    "sec_confidence": sec_conf if 'sec_conf' in locals() else None,
                    "av_metrics": avm if 'avm' in locals() else None,
                    "insiders_summary": ins_summary if 'ins_summary' in locals() else None,
                    "llm_memo": memo_text,
                    "sources": [s for s in sources if s],
                },
            )
            print(f"[run] Report written to: {out_file}")
        else:
            print("[run] Skipping report generation: --ticker is required for output path.")
        return 0

    print(
        "[run] Step 2 (Ticker→CIK) not implemented. Provide --cik to proceed with Step 3."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
