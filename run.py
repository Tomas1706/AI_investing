#!/usr/bin/env python3
import argparse
from datetime import datetime
from pathlib import Path

from config import load_config


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

    # Stub: for step 1 we only set up CLI and config
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

    # Step 1 success criteria ends here; further steps will be implemented next.
    print("[run] CLI scaffolding OK. Proceed to Step 2 (Ticker→CIK).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

