"""
Run an advanced sweep for mtf_feature_filtered_strategy.

Usage:
    python scripts/run_feature_filter_sweep.py
    python scripts/run_feature_filter_sweep.py --focused
    python scripts/run_feature_filter_sweep.py --candles 20000
    python scripts/run_feature_filter_sweep.py --full

This is research-only backtesting. It does not execute live trades.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_strategy_lab import QUICK_CANDLES, select_strategy_lab_data
from src.data_feed.market_data import load_csv_data
from src.features.feature_engine import build_features
from src.main import build_backtest_config, build_strategy_config
from src.settings import load_settings
from src.strategy_lab.feature_filter_sweep import (
    DEFAULT_SWEEP_REPORT_PATH,
    SWEEP_COLUMNS,
    build_focused_feature_filter_variants,
    build_feature_filter_variants,
    filter_fallback_sweep_results,
    filter_primary_sweep_results,
    run_feature_filter_sweep,
    sort_sweep_results,
)


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse feature-filter sweep command line options."""
    parser = argparse.ArgumentParser(description="Run feature-filter strategy sweep.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Use the full local CSV history.",
    )
    parser.add_argument(
        "--focused",
        action="store_true",
        help="Run the reduced higher-signal sweep grid.",
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


def main() -> None:
    """Run the feature-filter sweep."""
    args = parse_args()

    print("=" * 60)
    print("XAU Auto Trader - Feature Filter Sweep")
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
    sweep_df = select_strategy_lab_data(
        df,
        full=args.full,
        candles=args.candles,
    )

    if args.full:
        print(f"Mode: full history ({len(sweep_df)} candles)")
    else:
        requested_candles = args.candles if args.candles is not None else QUICK_CANDLES
        print(f"Mode: quick ({len(sweep_df)} of {len(df)} candles, requested {requested_candles})")

    print("Building feature columns once...")
    feature_df = build_features(sweep_df)

    variants = build_focused_feature_filter_variants() if args.focused else build_feature_filter_variants()
    sweep_mode = "focused" if args.focused else "full grid"
    print(f"Sweep mode: {sweep_mode}")
    print(f"Variants: {len(variants)}")
    print("")

    strategy_config = build_strategy_config(settings)
    backtest_config = replace(build_backtest_config(settings), allowed_sessions=None)

    comparison = run_feature_filter_sweep(
        df=feature_df,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        variants=variants,
        output_path=DEFAULT_SWEEP_REPORT_PATH,
        show_progress=True,
    )

    print("")
    print_top_results(comparison)
    print("")
    print(f"Sweep report exported: {DEFAULT_SWEEP_REPORT_PATH}")
    print("Important: this is backtesting research only, not live trading.")


def print_top_results(comparison) -> None:
    """Print quality-focused top result tables."""
    primary = filter_primary_sweep_results(comparison)

    if not primary.empty:
        print("Top 20 variants with total_trades >= 100, net_profit > 0, max_drawdown > 0:")
        print(sort_sweep_results(primary).head(20)[SWEEP_COLUMNS].to_string(index=False))
        return

    print("No variants found with total_trades >= 100, net_profit > 0, max_drawdown > 0.")

    fallback = filter_fallback_sweep_results(comparison)
    if not fallback.empty:
        print("")
        print("Top 20 variants with total_trades >= 50:")
        print(sort_sweep_results(fallback).head(20)[SWEEP_COLUMNS].to_string(index=False))

    print("")
    print("Top 20 variants by total_trades:")
    top_by_trades = comparison.sort_values(
        by=["total_trades", "profit_factor", "net_profit"],
        ascending=[False, False, False],
    ).head(20)
    print(top_by_trades[SWEEP_COLUMNS].to_string(index=False))


if __name__ == "__main__":
    main()
