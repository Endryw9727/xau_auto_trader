"""
Run daily coverage sweep for the final V50 balanced strategy.

The sweep is research-only backtesting. It does not execute trades.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_feed.market_data import load_csv_data
from src.main import build_backtest_config, build_strategy_config
from src.settings import load_settings
from src.strategy_lab.v50_daily_coverage_sweep import (
    DEFAULT_DAILY_COVERAGE_SWEEP_PATH,
    run_v50_daily_coverage_sweep,
    sort_daily_coverage_sweep,
)


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Run the V50 daily coverage sweep from local data."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Daily Coverage Sweep")
    print("=" * 72)

    settings = load_settings()
    if not RAW_DATA_PATH.exists():
        print(f"CSV file not found: {RAW_DATA_PATH}")
        print("Create this file first: data/raw/xauusd.csv")
        return

    print(f"Symbol: {settings.trading.symbol}")
    print(f"Base timeframe: {settings.trading.base_timeframe}")
    print(f"Live mode: {settings.trading.live_mode}")
    print("Mode: research/backtest only")
    print("")

    df = load_csv_data(RAW_DATA_PATH)
    strategy_config = build_strategy_config(settings)
    backtest_config = replace(build_backtest_config(settings), allowed_sessions=None)

    report = run_v50_daily_coverage_sweep(
        df=df,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        output_path=DEFAULT_DAILY_COVERAGE_SWEEP_PATH,
        show_progress=True,
    )

    print("")
    print("Daily coverage sweep:")
    print(sort_daily_coverage_sweep(report).to_string(index=False))
    print("")
    print(f"Daily coverage sweep exported: {DEFAULT_DAILY_COVERAGE_SWEEP_PATH}")
    print("No variant was promoted automatically.")


if __name__ == "__main__":
    main()
