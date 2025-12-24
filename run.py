#!/usr/bin/env python3
import argparse
from datetime import datetime
from pathlib import Path

from config import load_config
from sec import fetch_filings


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
        return 0

    print(
        "[run] Step 2 (Ticker→CIK) not implemented. Provide --cik to proceed with Step 3."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
