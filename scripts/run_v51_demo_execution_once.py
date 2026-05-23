"""Run one V51 demo-only MT5 execution attempt."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.execution.v51_demo_executor import (
    DEFAULT_V51_DEMO_OUTPUT_DIR,
    build_v51_demo_status,
    run_v51_demo_execution_once,
)
from src.strategy_lab.strategy_v51_demo_intraday import DEFAULT_V51_CONFIG_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Evaluate and log without submitting to MT5.")
    mode.add_argument("--execute-demo", action="store_true", help="Submit only to verified MT5 demo if all gates pass.")
    mode.add_argument("--status", action="store_true", help="Print V51 demo execution readiness without trading.")
    parser.add_argument("--config", type=Path, default=DEFAULT_V51_CONFIG_PATH, help="V51 strategy config path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_V51_DEMO_OUTPUT_DIR, help="V51 demo log directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dry_run = not args.execute_demo

    print("=" * 72)
    print("XAU Auto Trader - V51 Demo Execution Once")
    print("=" * 72)
    print("Mode: STATUS" if args.status else "Mode: DRY_RUN" if dry_run else "Mode: EXECUTE_DEMO")
    print(f"Config: {args.config}")
    print(f"Output dir: {args.output_dir}")

    if args.status:
        status = build_v51_demo_status(config_path=args.config, output_dir=args.output_dir)
        for key, value in status.items():
            print(f"{key}: {value}")
        print("No real live execution is enabled.")
        return

    try:
        result = run_v51_demo_execution_once(
            config_path=args.config,
            output_dir=args.output_dir,
            dry_run=dry_run,
        )
    except Exception as exc:
        print(f"Status: ERROR")
        print(f"Accepted: False")
        print(f"Reason: {exc}")
        print("No real live execution is enabled.")
        raise

    print(f"Signal id: {result.signal_id}")
    print(f"Candle time: {result.candle_time}")
    print(f"Side: {result.side}")
    print(f"Status: {result.status}")
    print(f"Accepted: {result.accepted}")
    print(f"Reason: {result.reason}")
    print("No real live execution is enabled.")


if __name__ == "__main__":
    main()
