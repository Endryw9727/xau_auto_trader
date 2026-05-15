"""Import MT5-exported CSV candles into local project data paths."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.market_data.mt5_csv_bridge import import_mt5_csv_bridge


def main() -> None:
    """Run the MT5 CSV bridge import and print a concise report."""
    print("=" * 72)
    print("XAU Auto Trader - MT5 CSV Bridge Import")
    print("=" * 72)

    try:
        results = import_mt5_csv_bridge()
    except Exception as exc:
        print("Status: ERROR")
        print(f"Reason: {exc}")
        print("No broker execution exists in this script.")
        return

    for result in results:
        before = result.last_timestamp_before.isoformat() if result.last_timestamp_before is not None else "n/a"
        after = result.last_timestamp_after.isoformat() if result.last_timestamp_after is not None else "n/a"
        print("-" * 72)
        print(f"Timeframe: {result.timeframe}")
        print(f"Source file: {result.source_file}")
        print(f"Rows read: {result.rows_read}")
        print(f"Rows before: {result.rows_before}")
        print(f"Rows after: {result.rows_after}")
        print(f"Added rows: {result.added_rows}")
        print(f"Last candle before: {before}")
        print(f"Last candle after: {after}")
        print(f"Status: {result.status}")
        print(f"Reason: {result.reason}")

    print("-" * 72)
    print("No trades were opened. This is CSV import only.")
    print("Next checks:")
    print(".venv/bin/python scripts/check_data_freshness.py")
    print(".venv/bin/python scripts/paper_preflight_check.py")


if __name__ == "__main__":
    main()
