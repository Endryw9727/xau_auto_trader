"""Run the isolated V2 shadow report for V1 diagnostics."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.v2_shadow.report import (  # noqa: E402
    DEFAULT_CANDIDATE_LOG_PATH,
    DEFAULT_MARKET_DATA_PATH,
    DEFAULT_SHADOW_OUTPUT_DIR,
    run_v2_shadow_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Run report-only mode. This never sends orders.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_MARKET_DATA_PATH, help="V1 OHLCV CSV path.")
    parser.add_argument("--candidate-log", type=Path, default=DEFAULT_CANDIDATE_LOG_PATH, help="V1 V51 execution log path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_SHADOW_OUTPUT_DIR, help="Shadow output directory.")
    parser.add_argument("--limit-candles", type=int, default=500, help="Maximum candles to load for diagnostics.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_v2_shadow_report(
        market_data_path=args.csv,
        candidate_log_path=args.candidate_log,
        output_dir=args.output_dir,
        dry_run=True,
        limit_candles=args.limit_candles,
    )
    print("V2 shadow report complete")
    print(f"Status: {report.status}")
    print(f"JSON: {args.output_dir / 'v2_shadow_latest.json'}")
    print(f"TXT: {args.output_dir / 'v2_shadow_latest.txt'}")
    print("Report-only: no broker, execution, position, scheduler, or live trading call was made.")


if __name__ == "__main__":
    main()
