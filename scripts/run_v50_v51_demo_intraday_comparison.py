"""Run a V50 high-margin vs V51 demo intraday comparison from local CSV data."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_feed.market_data import load_csv_data
from src.strategy_lab.strategy_v51_demo_intraday import (
    DEFAULT_V50_V51_COMPARISON_PATH,
    DEFAULT_V51_CONFIG_PATH,
    run_v50_vs_v51_comparison,
)


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=RAW_DATA_PATH, help="OHLCV CSV path.")
    parser.add_argument("--config", type=Path, default=DEFAULT_V51_CONFIG_PATH, help="V51 config path.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_V50_V51_COMPARISON_PATH.parent,
        help="Directory for comparison and signal logs.",
    )
    parser.add_argument("--candles", type=int, default=5000, help="Use only the latest N candles; use 0 for all.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("=" * 72)
    print("XAU Auto Trader - V50 vs V51 Demo Intraday Comparison")
    print("=" * 72)
    print("Mode: research/demo-safe comparison only")
    print(f"Input CSV: {args.csv}")
    print(f"V51 config: {args.config}")

    market_data = load_csv_data(args.csv)
    if args.candles > 0:
        market_data = market_data.tail(args.candles)

    comparison, v50_log, v51_log = run_v50_vs_v51_comparison(
        market_data,
        v51_config_path=args.config,
        output_dir=args.output_dir,
    )

    print("")
    print(comparison.to_string(index=False))
    print("")
    print(f"V50 log rows: {len(v50_log)}")
    print(f"V51 log rows: {len(v51_log)}")
    print(f"Comparison exported: {args.output_dir / DEFAULT_V50_V51_COMPARISON_PATH.name}")
    print("No real live execution is enabled.")


if __name__ == "__main__":
    main()
