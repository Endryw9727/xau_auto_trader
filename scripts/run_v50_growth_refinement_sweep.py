"""
Run targeted refinement sweeps for v50_growth_long_all_short_london_strategy.

Usage:
    python scripts/run_v50_growth_refinement_sweep.py
    python scripts/run_v50_growth_refinement_sweep.py --period quarter
    python scripts/run_v50_growth_refinement_sweep.py --period month

This is research-only backtesting. It does not execute trades.
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
from src.strategy_lab.v50_growth_refinement_sweep import (
    DEFAULT_GROWTH_REFINEMENT_SWEEP_PATH,
    PERIOD_CHOICES,
    growth_refinement_walk_forward_path,
    run_v50_growth_refinement_sweep,
    run_v50_growth_refinement_walk_forward,
    sort_growth_refinement_sweep,
    sort_growth_refinement_walk_forward,
)


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse growth-refinement sweep options."""
    parser = argparse.ArgumentParser(description="Run V50 growth-refinement sweep.")
    parser.add_argument(
        "--period",
        choices=PERIOD_CHOICES,
        default=None,
        help="Run walk-forward mode with the selected calendar period.",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Run the V50 growth-refinement sweep from local data."""
    args = parse_args()

    print("=" * 72)
    print("XAU Auto Trader - V50 Growth Refinement Sweep")
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

    if args.period:
        output_path = growth_refinement_walk_forward_path(args.period)
        print(f"Running walk-forward refinement: period={args.period}")
        report = run_v50_growth_refinement_walk_forward(
            df=df,
            period=args.period,
            strategy_config=strategy_config,
            backtest_config=backtest_config,
            output_path=output_path,
            show_progress=True,
        )
        print("")
        print("Walk-forward refinement summary:")
        print(sort_growth_refinement_walk_forward(report).to_string(index=False))
        print("")
        print(f"Walk-forward refinement exported: {output_path}")
    else:
        print("Running full-history refinement sweep")
        report = run_v50_growth_refinement_sweep(
            df=df,
            strategy_config=strategy_config,
            backtest_config=backtest_config,
            output_path=DEFAULT_GROWTH_REFINEMENT_SWEEP_PATH,
            show_progress=True,
        )
        print("")
        print("Full-history refinement summary:")
        print(sort_growth_refinement_sweep(report).to_string(index=False))
        print("")
        print(f"Refinement sweep exported: {DEFAULT_GROWTH_REFINEMENT_SWEEP_PATH}")

    print("No variant was promoted automatically.")


if __name__ == "__main__":
    main()
