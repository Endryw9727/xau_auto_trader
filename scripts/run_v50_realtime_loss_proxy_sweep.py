"""
Run realtime-safe V50 loss proxy sweep and stress test.

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
from src.strategy_lab.v50_realtime_loss_proxy_sweep import (
    DEFAULT_REALTIME_LOSS_PROXY_STRESS_PATH,
    DEFAULT_REALTIME_LOSS_PROXY_SWEEP_PATH,
    run_realtime_loss_proxy_stress,
    run_realtime_loss_proxy_sweep,
)


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Run realtime-safe proxy sweep from local data."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Realtime Loss Proxy Sweep")
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

    sweep = run_realtime_loss_proxy_sweep(
        df=df,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        output_path=DEFAULT_REALTIME_LOSS_PROXY_SWEEP_PATH,
        show_progress=True,
    )
    stress = run_realtime_loss_proxy_stress(
        df=df,
        sweep_report=sweep,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        output_path=DEFAULT_REALTIME_LOSS_PROXY_STRESS_PATH,
        show_progress=True,
    )

    print("")
    print("Realtime loss proxy sweep:")
    print(sweep.to_string(index=False))
    print("")
    print("Realtime loss proxy stress:")
    print(stress.to_string(index=False))
    print("")
    print(f"Realtime proxy sweep exported: {DEFAULT_REALTIME_LOSS_PROXY_SWEEP_PATH}")
    print(f"Realtime proxy stress exported: {DEFAULT_REALTIME_LOSS_PROXY_STRESS_PATH}")
    print("No variant was promoted automatically.")


if __name__ == "__main__":
    main()
