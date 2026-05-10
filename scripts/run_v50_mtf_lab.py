"""
Run the V50 Pine MTF research candidate on local multi-timeframe CSV files.

This is backtesting research only. It does not execute trades.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.backtesting.backtester import run_backtest
from src.backtesting.metrics import metrics_to_dict
from src.main import build_backtest_config, build_strategy_config
from src.market_data.timeframe_loader import load_xauusd_timeframes
from src.settings import load_settings
from src.strategy_lab import strategy_v50_pine
from src.strategy_lab.v50_mtf_features import build_v50_mtf_dataset


TIMEFRAMES_DIR = Path("data/raw/timeframes")


def main() -> None:
    print("=" * 60)
    print("XAU Auto Trader - V50 Pine MTF Lab")
    print("=" * 60)

    settings = load_settings()
    print(f"Symbol: {settings.trading.symbol}")
    print(f"Live mode: {settings.trading.live_mode}")
    print("Mode: research/backtest only")
    print("")

    timeframes = load_xauusd_timeframes(TIMEFRAMES_DIR)
    mtf_data = build_v50_mtf_dataset(timeframes)

    strategy_config = replace(build_strategy_config(settings), timeframe="5m")
    backtest_config = replace(build_backtest_config(settings), allowed_sessions=None)

    def signal_generator(window, config):
        return strategy_v50_pine.generate_mtf_signal(window, config)

    signal_generator.required_history_candles = strategy_v50_pine.REQUIRED_HISTORY_CANDLES

    result = run_backtest(
        df=mtf_data,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        save_signals=False,
        save_trades_to_db=False,
        save_signals_to_db=False,
        signal_generator=signal_generator,
        strategy_name=strategy_v50_pine.MTF_STRATEGY_NAME,
    )
    metrics = metrics_to_dict(result.metrics)

    print(f"Dataset rows: {len(mtf_data)}")
    print(f"Time start: {mtf_data['time'].min()}")
    print(f"Time end: {mtf_data['time'].max()}")
    print("")
    print(f"total_trades: {metrics['total_trades']}")
    print(f"win_rate: {metrics['win_rate']:.2f}")
    print(f"profit_factor: {metrics['profit_factor']:.4f}")
    print(f"net_profit: {metrics['net_profit']:.2f}")
    print(f"max_drawdown: {metrics['max_drawdown']:.2f}")
    print(f"expectancy: {metrics['expectancy']:.4f}")
    print("")
    print("Important: V50 MTF Lab is backtesting only, not live trading.")


if __name__ == "__main__":
    main()
