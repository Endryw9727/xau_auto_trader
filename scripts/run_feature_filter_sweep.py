"""
Run an advanced sweep for mtf_feature_filtered_strategy.

Usage:
    python scripts/run_feature_filter_sweep.py
    python scripts/run_feature_filter_sweep.py --focused
    python scripts/run_feature_filter_sweep.py --relaxed --candles 20000
    python scripts/run_feature_filter_sweep.py --relaxed --full
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
    build_relaxed_feature_filter_variants,
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
        "--relaxed",
        action="store_true",
        help="Run the reduced more permissive sweep grid.",
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

    if args.focused and args.relaxed:
        parser.error("--focused and --relaxed cannot be used together")

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

    variants, sweep_mode = select_sweep_variants(args)
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


def select_sweep_variants(args):
    """Select sweep variants from command line options."""
    if args.relaxed:
        return build_relaxed_feature_filter_variants(), "relaxed"
    if args.focused:
        return build_focused_feature_filter_variants(), "focused"
    return build_feature_filter_variants(), "full grid"


def print_top_results(comparison) -> None:
    """Print top result tables while avoiding tiny-sample winners."""
    high_trade = comparison[comparison["total_trades"] >= 250]
    eligible = comparison[comparison["total_trades"] >= 100]

    _print_table(
        "Top 20 variants with total_trades >= 250:",
        sort_sweep_results(high_trade).head(20),
    )

    primary = filter_primary_sweep_results(comparison)
    _print_table(
        "Top 20 variants with total_trades >= 100, net_profit > 0, max_drawdown > 0:",
        sort_sweep_results(primary).head(20),
    )

    if not eligible.empty:
        _print_table(
            "Top 20 variants by profit_factor with total_trades >= 100:",
            sort_sweep_results(eligible).head(20),
        )
        _print_table(
            "Top 20 variants by net_profit with total_trades >= 100:",
            eligible.sort_values(
                by=["net_profit", "profit_factor", "max_drawdown"],
                ascending=[False, False, True],
            ).head(20),
        )
        _print_table(
            "Top 20 low-drawdown variants with total_trades >= 100 and net_profit > 0:",
            eligible[
                (eligible["net_profit"] > 0)
                & (eligible["max_drawdown"] > 0)
            ].sort_values(
                by=["max_drawdown", "net_profit", "profit_factor"],
                ascending=[True, False, False],
            ).head(20),
        )
        _print_table(
            "Top 20 variants by total_trades with total_trades >= 100:",
            eligible.sort_values(
                by=["total_trades", "profit_factor", "net_profit"],
                ascending=[False, False, False],
            ).head(20),
        )
        return

    print("No variants found with total_trades >= 100. Lower-trade tables are diagnostic only.")

    fallback = filter_fallback_sweep_results(comparison)
    if not fallback.empty:
        _print_table(
            "Diagnostic top 20 variants with total_trades >= 50:",
            sort_sweep_results(fallback).head(20),
        )

    _print_table(
        "Diagnostic top 20 variants by total_trades:",
        comparison.sort_values(
            by=["total_trades", "profit_factor", "net_profit"],
            ascending=[False, False, False],
        ).head(20),
    )


def _print_table(title: str, table) -> None:
    print("")
    print(title)
    if table.empty:
        print("No matching variants.")
        return
    print(table[SWEEP_COLUMNS].to_string(index=False))


if __name__ == "__main__":
    main()
