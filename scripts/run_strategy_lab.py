"""
Run Strategy Lab comparison from local CSV data.

Usage:
    python scripts/run_strategy_lab.py

This is research-only backtesting. It does not execute live trades.
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
from src.strategy_lab.lab import run_strategy_lab


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Run the Strategy Lab comparison."""
    print("=" * 60)
    print("XAU Auto Trader - Strategy Lab")
    print("=" * 60)

    settings = load_settings()

    if not RAW_DATA_PATH.exists():
        print(f"CSV file not found: {RAW_DATA_PATH}")
        print("Create this file first:")
        print("data/raw/xauusd.csv")
        return

    print(f"Symbol: {settings.trading.symbol}")
    print(f"Base timeframe: {settings.trading.base_timeframe}")
    print(f"Live mode: {settings.trading.live_mode}")
    print("")

    df = load_csv_data(RAW_DATA_PATH)
    strategy_config = build_strategy_config(settings)
    backtest_config = replace(build_backtest_config(settings), allowed_sessions=None)

    result = run_strategy_lab(
        df=df,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
    )

    print("Strategy comparison:")
    print(result.comparison[["strategy_name", "total_trades", "net_profit", "win_rate", "max_drawdown"]])
    print("")
    print(f"Comparison report exported: {result.report_path}")
    print("Important: Strategy Lab is backtesting only, not live trading.")


if __name__ == "__main__":
    main()
