"""
Check local market-data freshness for paper-forward.

This script reads local CSV data only. It does not fetch data, contact brokers,
or enable live trading.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.market_data.data_freshness import (
    DEFAULT_XAUUSD_CSV_PATH,
    analyze_data_freshness,
    append_freshness_log,
)


def main() -> None:
    """Print local data freshness status and append the paper-forward log."""
    print("=" * 72)
    print("XAU Auto Trader - Data Freshness Check")
    print("=" * 72)

    report = analyze_data_freshness(DEFAULT_XAUUSD_CSV_PATH, symbol="XAUUSD")
    append_freshness_log(report)

    latest = report.latest_timestamp.isoformat() if report.latest_timestamp is not None else "n/a"
    age = "n/a" if report.age_minutes is None else f"{report.age_minutes:.1f} min"

    print(f"Symbol: {report.symbol}")
    print(f"Timeframe: {report.timeframe}")
    print(f"Latest candle: {latest}")
    print(f"Latest candle age: {age}")
    print(f"Rows: {report.row_count}")
    print(f"Gaps found: {report.gap_count}")
    print(f"Missing candles: {report.missing_candles}")
    print(f"Missing expected candle: {report.missing_expected_candle}")
    if report.error:
        print(f"Error: {report.error}")
    print(f"Status: {report.status}")
    print("")
    print("No live trading was enabled. This is a local paper/research check.")


if __name__ == "__main__":
    main()
