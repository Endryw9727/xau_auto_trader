"""Update local market-data CSV files from MT5 read-only candles."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.market_data.mt5_readonly_data_updater import update_market_data_from_mt5_readonly


def main() -> None:
    """Run a safe read-only market-data update."""
    print("=" * 72)
    print("XAU Auto Trader - MT5 Read-Only Market Data Update")
    print("=" * 72)

    try:
        results = update_market_data_from_mt5_readonly()
    except Exception as exc:
        print("Status: ERROR")
        print(f"Reason: {exc}")
        print("No trades were opened. No broker execution is available from this script.")
        return

    for result in results:
        before = result.last_timestamp_before.isoformat() if result.last_timestamp_before is not None else "n/a"
        after = result.last_timestamp_after.isoformat() if result.last_timestamp_after is not None else "n/a"
        print("-" * 72)
        print(f"Symbol: {result.symbol}")
        print(f"Timeframe: {result.timeframe}")
        print(f"Rows before: {result.rows_before}")
        print(f"Rows after: {result.rows_after}")
        print(f"Last candle before: {before}")
        print(f"Last candle after: {after}")
        print(f"Added rows: {result.added_rows}")
        print(f"Status: {result.status}")
        print(f"Reason: {result.reason}")

    print("-" * 72)
    print("No trades were opened. This script only reads MT5 candles when available.")
    print("Next check:")
    print(".venv/bin/python scripts/check_data_freshness.py")


if __name__ == "__main__":
    main()
