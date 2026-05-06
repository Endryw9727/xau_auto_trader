"""
Run paper trading simulation from local CSV data.

Usage:
    python scripts/run_paper_trading.py

Expected CSV:
    data/raw/xauusd.csv

This is not live trading.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_feed.market_data import load_csv_data
from src.execution.paper_trading_engine import (
    PaperTradingConfig,
    export_paper_trading_report,
    run_paper_trading_on_data,
)
from src.strategy.rules import StrategyConfig


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Run paper trading simulation."""
    print("=" * 60)
    print("XAU Auto Trader - Paper Trading Simulation")
    print("=" * 60)

    if not RAW_DATA_PATH.exists():
        print(f"CSV file not found: {RAW_DATA_PATH}")
        print("Run this first if you need fake data:")
        print("python scripts/generate_fake_xauusd_data.py")
        return

    df = load_csv_data(RAW_DATA_PATH)

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

    paper_config = PaperTradingConfig(
        initial_balance=1000.0,
        risk_per_trade=0.005,
        max_risk_per_trade=0.01,
        max_daily_loss=0.02,
        max_open_trades=1,
        max_consecutive_losses=3,
        min_risk_reward=2.0,
        value_per_point=1.0,
        commission_per_trade=0.0,
        slippage_points=0.0,
        warmup_candles=220,
    )

    result = run_paper_trading_on_data(
        df=df,
        strategy_config=strategy_config,
        paper_config=paper_config,
    )

    trades_path = export_paper_trading_report(result)

    print("")
    print("=" * 60)
    print("PAPER TRADING RESULTS")
    print("=" * 60)
    print(f"Initial balance: {paper_config.initial_balance:.2f}")
    print(f"Final balance:   {result.final_balance:.2f}")
    print(f"Net profit:      {result.net_profit:.2f}")
    print(f"Total trades:    {result.total_trades}")
    print(f"Wins:            {result.wins}")
    print(f"Losses:          {result.losses}")
    print(f"Breakeven:       {result.breakeven}")
    print("")
    print(f"Report exported: {trades_path}")
    print("")
    print("Important: this is paper trading simulation only, not live trading.")


if __name__ == "__main__":
    main()
