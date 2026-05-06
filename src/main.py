"""
Main entry point for running a local XAU/USD backtest.

Usage:
    python -m src.main

Expected CSV file:
    data/raw/xauusd.csv

Expected CSV columns:
    Date, Open, High, Low, Close, Volume

This script does not execute real trades.
It only runs a local backtest and exports reports.
"""

from __future__ import annotations

from pathlib import Path

from src.backtesting.backtester import BacktestConfig, export_backtest_report, run_backtest
from src.backtesting.metrics import metrics_to_dict
from src.data_feed.market_data import load_csv_data
from src.strategy.rules import StrategyConfig


RAW_DATA_PATH = Path("data/raw/xauusd.csv")
REPORT_DIR = Path("reports/backtests")


def main() -> None:
    """Run a local backtest from CSV data."""
    print("=" * 60)
    print("XAU Auto Trader - Local Backtest")
    print("=" * 60)

    if not RAW_DATA_PATH.exists():
        print(f"CSV file not found: {RAW_DATA_PATH}")
        print("")
        print("Create this file first:")
        print("data/raw/xauusd.csv")
        print("")
        print("Required columns:")
        print("Date, Open, High, Low, Close, Volume")
        return

    print(f"Loading market data from: {RAW_DATA_PATH}")
    df = load_csv_data(RAW_DATA_PATH)

    print(f"Loaded candles: {len(df)}")
    print(f"From: {df.index.min()}")
    print(f"To:   {df.index.max()}")
    print("")

    strategy_config = StrategyConfig(
        symbol="XAUUSD",
        timeframe="15m",
        min_adx=18.0,
        min_risk_reward=2.0,
        atr_multiplier_sl=1.5,
        atr_multiplier_tp=3.0,
        rsi_buy_max=70.0,
        rsi_sell_min=30.0,
    )

    backtest_config = BacktestConfig(
        initial_balance=1000.0,
        risk_per_trade=0.005,
        max_daily_loss=0.02,
        max_open_trades=1,
        max_consecutive_losses=3,
        min_risk_reward=2.0,
        value_per_point=1.0,
        commission_per_trade=0.0,
        slippage_points=0.0,
        warmup_candles=220,
    )

    print("Running backtest...")
    result = run_backtest(
        df=df,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
    )

    trades_path, metrics_path = export_backtest_report(result, REPORT_DIR)
    metrics = metrics_to_dict(result.metrics)

    print("")
    print("=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)

    print(f"Initial balance:        {backtest_config.initial_balance:.2f}")
    print(f"Final balance:          {result.final_balance:.2f}")
    print(f"Net profit:             {metrics['net_profit']:.2f}")
    print(f"Total trades:           {metrics['total_trades']}")
    print(f"Wins:                   {metrics['wins']}")
    print(f"Losses:                 {metrics['losses']}")
    print(f"Breakeven:              {metrics['breakeven']}")
    print(f"Win rate:               {metrics['win_rate']:.2f}%")
    print(f"Profit factor:          {metrics['profit_factor']:.2f}")
    print(f"Expectancy:             {metrics['expectancy']:.2f}")
    print(f"Max drawdown:           {metrics['max_drawdown']:.2f}")
    print(f"Max consecutive wins:   {metrics['max_consecutive_wins']}")
    print(f"Max consecutive losses: {metrics['max_consecutive_losses']}")

    print("")
    print("Reports exported:")
    print(f"- {trades_path}")
    print(f"- {metrics_path}")
    print("")
    print("Important: this is a backtest only, not live trading.")


if __name__ == "__main__":
    main()
