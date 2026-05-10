"""
Inspect local XAUUSD multi-timeframe CSV files.

This script is research-only and reads local files from data/raw/timeframes.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.market_data.timeframe_loader import load_xauusd_timeframes


DEFAULT_BASE_DIR = Path("data/raw/timeframes")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect local multi-timeframe CSV files.")
    parser.add_argument(
        "--base-dir",
        default=str(DEFAULT_BASE_DIR),
        help="Directory containing XAUUSD_M1/M5/M15/M30/H1/H4 CSV files.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    frames = load_xauusd_timeframes(args.base_dir)

    print("=" * 72)
    print("XAUUSD Multi-Timeframe CSV Inspection")
    print("=" * 72)
    print(f"Base directory: {args.base_dir}")
    print("")

    for timeframe, data in frames.items():
        has_real_volume = bool(data["has_real_volume"].all()) if not data.empty else False
        nan_counts = data.isna().sum()
        nan_summary = {
            column: int(count)
            for column, count in nan_counts.items()
            if int(count) > 0
        }

        print(f"Timeframe: {timeframe}")
        print(f"Rows: {len(data)}")
        print(f"Start: {data['time'].min() if not data.empty else 'n/a'}")
        print(f"End: {data['time'].max() if not data.empty else 'n/a'}")
        print(f"Columns: {', '.join(data.columns)}")
        print(f"Has real volume: {has_real_volume}")
        print(f"NaN: {nan_summary if nan_summary else 'none'}")
        print("-" * 72)

    print("Important: this inspection is local research/backtest data loading only.")


if __name__ == "__main__":
    main()

