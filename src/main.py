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
from src.settings import load_settings
from src.strategy.rules import StrategyConfig


RAW_DATA_PATH = Path("data/raw/xauusd.csv")
REPORT_DIR = Path("reports/backtests")


def main() -> None:
    """Run a local backtest from CSV data."""
    print("=" * 60)
    print("XAU Auto Trader - Local Backtest")
    print("=" * 60)

    settings = load_settings()

    if not RAW_DATA_PATH.exists():
        print(f"CSV file not found: {RAW_DATA_PATH}")
        print("")
        print("Create this file first:")
        print("data/raw/xauusd.csv")
        print("")
        print("Required columns:")
        print("Date, Open, High, Low, Close, Volume")
        return

    print(f"Symbol: {settings.trading.symbol}")
    print(f"Base timeframe: {settings.trading.base_timeframe}")
    print(f"Live mode: {settings.trading.live_mode}")
    print("")

    print(f"Loading market data from: {RAW_DATA_PATH}")
    df = load_csv_data(RAW_DATA_PATH)

    print(f"Loaded candles: {len(df)}")
    print(f"From: {df.index.min()}")
    print(f"To:   {df.index.max()}")
    print("")

    strategy_config = StrategyConfig(
        symbol=settings.trading.symbol,
        timeframe=settings.trading.base_timeframe,
        min_adx=settings.filters.min_adx,
        min_risk_reward=settings.risk.min_risk_reward,
        atr_multiplier_sl=settings.strategy.atr_multiplier_sl,
        atr_multiplier_tp=settings.strategy.atr_multiplier_tp,
        rsi_buy_max=settings.strategy.rsi_buy_max,
        rsi_sell_min=settings.strategy.rsi_sell_min,
    )

    backtest_config = BacktestConfig(
        initial_balance=settings.backtest.initial_balance,
        risk_per_trade=settings.risk.risk_per_trade,
        max_daily_loss=settings.risk.max_daily_loss,
        max_open_trades=1,
        max_consecutive_losses=settings.risk.max_consecutive_losses,
        min_risk_reward=settings.risk.min_risk_reward,
        value_per_point=settings.risk.value_per_point,
        commission_per_trade=settings.backtest.commission_per_trade,
        slippage_points=settings.backtest.slippage_points,
        warmup_candles=settings.backtest.warmup_candles,
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
