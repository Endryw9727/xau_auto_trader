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
from src.settings import load_settings
from src.strategy.rules import StrategyConfig


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Run paper trading simulation."""
    print("=" * 60)
    print("XAU Auto Trader - Paper Trading Simulation")
    print("=" * 60)

    settings = load_settings()

    if not RAW_DATA_PATH.exists():
        print(f"CSV file not found: {RAW_DATA_PATH}")
        print("Run this first if you need fake data:")
        print("python scripts/generate_fake_xauusd_data.py")
        return

    print(f"Symbol: {settings.trading.symbol}")
    print(f"Base timeframe: {settings.trading.base_timeframe}")
    print(f"Live mode: {settings.trading.live_mode}")
    print("")

    df = load_csv_data(RAW_DATA_PATH)

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

    paper_config = PaperTradingConfig(
        initial_balance=settings.backtest.initial_balance,
        risk_per_trade=settings.risk.risk_per_trade,
        max_risk_per_trade=settings.risk.max_risk_per_trade,
        max_daily_loss=settings.risk.max_daily_loss,
        max_open_trades=settings.risk.max_open_trades,
        max_consecutive_losses=settings.risk.max_consecutive_losses,
        min_risk_reward=settings.risk.min_risk_reward,
        value_per_point=settings.risk.value_per_point,
        commission_per_trade=settings.backtest.commission_per_trade,
        slippage_points=settings.backtest.slippage_points,
        warmup_candles=settings.backtest.warmup_candles,
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
