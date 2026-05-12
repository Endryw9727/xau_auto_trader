"""
Run controlled paper simulation for the selected V50 candidates.

This script uses local historical data and local backtest trades only. It does
not connect to any execution venue and does not place real orders.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.backtesting.backtester import BacktestConfig
from src.data_feed.market_data import load_csv_data
from src.paper.paper_engine import (
    DEFAULT_PAPER_CONFIG_PATH,
    DEFAULT_PAPER_DAILY_SUMMARY_PATH,
    DEFAULT_PAPER_EQUITY_CURVE_PATH,
    DEFAULT_PAPER_SUMMARY_PATH,
    DEFAULT_PAPER_TRADES_PATH,
    load_paper_trading_config,
    run_controlled_paper_simulation,
)
from src.strategy.rules import StrategyConfig
from src.strategy_lab.v50_cost_aware import run_axi_source_backtests


RAW_DATA_PATH = Path("data/raw/xauusd.csv")

DISPLAY_COLUMNS = [
    "strategy_name",
    "starting_equity",
    "ending_equity",
    "net_profit",
    "profit_factor_net",
    "max_dd_pct",
    "max_dd_eur",
    "total_trades",
    "trades_per_day",
    "win_rate",
    "avg_win",
    "avg_loss",
    "expectancy",
    "max_consecutive_losses",
    "worst_day",
    "worst_week",
    "worst_month",
    "months_positive",
    "months_negative",
    "no_trade_days",
    "max_no_trade_days",
    "time_to_1500_if_reached",
    "time_to_2000_if_reached",
    "returned_below_1000_after_growth",
    "drawdown_over_8_pct",
    "drawdown_over_10_pct",
    "drawdown_over_12_pct",
]


def main() -> None:
    """Run the controlled paper simulation and print key metrics."""
    print("=" * 72)
    print("XAU Auto Trader - Controlled Paper Simulation")
    print("=" * 72)

    config = load_paper_trading_config(DEFAULT_PAPER_CONFIG_PATH)
    print(f"Config: {DEFAULT_PAPER_CONFIG_PATH}")
    print(f"Main strategy: {config.strategy_name}")
    print(f"Backup strategy: {config.backup_strategy}")
    print(f"live_mode: {config.live_mode}")
    print(f"paper_mode: {config.paper_mode}")
    print("Execution: local research/paper simulation only")

    if not RAW_DATA_PATH.exists():
        print(f"CSV file not found: {RAW_DATA_PATH}")
        return

    market_data = load_csv_data(RAW_DATA_PATH)
    print(f"Loaded candles: {len(market_data)}")

    source_results = run_axi_source_backtests(
        df=market_data,
        strategy_config=StrategyConfig(symbol=config.symbol, timeframe=config.base_timeframe),
        backtest_config=BacktestConfig(
            initial_balance=config.initial_equity,
            commission_per_trade=0.0,
            slippage_points=0.0,
            allowed_sessions=None,
            rolling_window_candles=500,
        ),
        show_progress=True,
    )

    summary, _paper_trades, _equity_curve, _daily_summary = run_controlled_paper_simulation(
        source_results=source_results,
        config=config,
        market_data=market_data,
    )

    print("")
    print("Paper summary:")
    printable = summary.copy()
    for column in DISPLAY_COLUMNS:
        if column not in printable.columns:
            printable[column] = None
    print(printable[DISPLAY_COLUMNS].to_string(index=False))
    print("")
    print(f"Summary exported: {DEFAULT_PAPER_SUMMARY_PATH}")
    print(f"Trades exported: {DEFAULT_PAPER_TRADES_PATH}")
    print(f"Equity curve exported: {DEFAULT_PAPER_EQUITY_CURVE_PATH}")
    print(f"Daily summary exported: {DEFAULT_PAPER_DAILY_SUMMARY_PATH}")
    print("No strategy was promoted automatically.")


if __name__ == "__main__":
    main()
