"""
Run Strategy Lab comparison from local CSV data.

Usage:
    python scripts/run_strategy_lab.py
    python scripts/run_strategy_lab.py --candles 20000
    python scripts/run_strategy_lab.py --full

This is research-only backtesting. It does not execute live trades.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_feed.market_data import load_csv_data
from src.main import build_backtest_config, build_strategy_config
from src.settings import load_settings
from src.strategy_lab.lab import run_strategy_lab
from src.strategy_lab.strategy_v50_candidates import export_v50_candidate_comparison


RAW_DATA_PATH = Path("data/raw/xauusd.csv")
QUICK_CANDLES = 5000


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse Strategy Lab command line options."""
    parser = argparse.ArgumentParser(description="Run Strategy Lab comparison.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Use the full local CSV history.",
    )
    parser.add_argument(
        "--candles",
        type=int,
        default=None,
        help=f"Use only the latest N candles. Default: {QUICK_CANDLES}.",
    )
    args = parser.parse_args(argv)

    if args.candles is not None and args.candles <= 0:
        parser.error("--candles must be a positive integer")

    return args


def select_strategy_lab_data(
    df,
    *,
    full: bool = False,
    candles: int | None = None,
):
    """Select the research window used by Strategy Lab."""
    if full:
        return df

    candle_limit = candles if candles is not None else QUICK_CANDLES
    if candle_limit <= 0:
        raise ValueError("candles must be positive")
    if len(df) <= candle_limit:
        return df

    return df.tail(candle_limit).copy()


def main() -> None:
    """Run the Strategy Lab comparison."""
    args = parse_args()

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
    lab_df = select_strategy_lab_data(
        df,
        full=args.full,
        candles=args.candles,
    )

    if args.full:
        print(f"Mode: full history ({len(lab_df)} candles)")
    else:
        requested_candles = args.candles if args.candles is not None else QUICK_CANDLES
        print(f"Mode: quick ({len(lab_df)} of {len(df)} candles, requested {requested_candles})")
    print("")

    strategy_config = build_strategy_config(settings)
    backtest_config = replace(build_backtest_config(settings), allowed_sessions=None)

    result = run_strategy_lab(
        df=lab_df,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        show_progress=True,
    )

    print("Strategy comparison:")
    print(
        result.comparison[
            [
                "strategy_name",
                "allowed_sessions",
                "risk_per_trade",
                "min_risk_reward",
                "total_trades",
                "net_profit",
                "win_rate",
                "max_drawdown",
            ]
        ]
    )
    print("")
    print(f"Comparison report exported: {result.report_path}")
    print(f"Trades by strategy exported: {result.trades_report_path}")
    candidate_path = export_v50_candidate_comparison(result.comparison)
    print(f"V50 candidate comparison exported: {candidate_path}")
    print("Important: Strategy Lab is backtesting only, not live trading.")


if __name__ == "__main__":
    main()
