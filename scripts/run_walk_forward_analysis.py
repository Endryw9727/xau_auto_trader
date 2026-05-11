"""
Run walk-forward period analysis for selected Strategy Lab strategies.

Usage:
    python scripts/run_walk_forward_analysis.py --period yearly
    python scripts/run_walk_forward_analysis.py --period half
    python scripts/run_walk_forward_analysis.py --period quarter
    python scripts/run_walk_forward_analysis.py --period month

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
from src.market_data.timeframe_loader import load_xauusd_timeframes
from src.settings import load_settings
from src.strategy_lab import strategy_v50_pine
from src.strategy_lab.v50_mtf_features import build_v50_mtf_dataset
from src.strategy_lab.strategy_diagnostics import build_strategy_diagnostics
from src.strategy_lab.strategy_v50_candidates import (
    FINAL_BALANCED_STRATEGY_NAME,
    FINAL_GROWTH_STRATEGY_NAME,
    FINAL_LOW_RISK_STRATEGY_NAME,
    PROXY_BALANCED_CANDIDATE_STRATEGY_NAME,
    export_v50_candidate_walk_forward,
)
from src.strategy_lab.walk_forward_analysis import (
    PERIOD_CHOICES,
    WALK_FORWARD_COLUMNS,
    WALK_FORWARD_REPORT_PATH,
    get_walk_forward_strategy_specs,
    run_walk_forward_analysis,
    summarize_walk_forward_results,
)


RAW_DATA_PATH = Path("data/raw/xauusd.csv")
TIMEFRAMES_DIR = Path("data/raw/timeframes")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse walk-forward analysis command line options."""
    parser = argparse.ArgumentParser(description="Run walk-forward period analysis.")
    parser.add_argument(
        "--period",
        choices=PERIOD_CHOICES,
        default="half",
        help="Calendar period split to use. Default: half.",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Run walk-forward period analysis from local CSV data."""
    args = parse_args()

    print("=" * 60)
    print("XAU Auto Trader - Walk-Forward Analysis")
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
    print(f"Period mode: {args.period}")
    print("")

    df = load_csv_data(RAW_DATA_PATH)
    strategy_config = build_strategy_config(settings)
    backtest_config = replace(build_backtest_config(settings), allowed_sessions=None)
    strategies = get_walk_forward_strategy_specs()
    strategy_datasets = _build_strategy_datasets(strategies)

    analysis = run_walk_forward_analysis(
        df=df,
        period=args.period,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        strategies=strategies,
        strategy_datasets=strategy_datasets,
        output_path=WALK_FORWARD_REPORT_PATH,
        show_progress=True,
    )
    summary = summarize_walk_forward_results(analysis)
    selected_v50_names = (
        FINAL_BALANCED_STRATEGY_NAME,
        PROXY_BALANCED_CANDIDATE_STRATEGY_NAME,
        FINAL_GROWTH_STRATEGY_NAME,
        FINAL_LOW_RISK_STRATEGY_NAME,
    )
    selected_v50_summary = build_strategy_diagnostics(analysis, strategy_names=selected_v50_names)
    candidate_report_path = export_v50_candidate_walk_forward(analysis, args.period)

    print("")
    print("Walk-forward table:")
    print(
        analysis.sort_values(["period_start", "strategy_name"])[WALK_FORWARD_COLUMNS].to_string(
            index=False,
        )
    )

    print("")
    print("Strategy summary:")
    print(summary.to_string(index=False))
    print("")
    print("Selected V50 candidate diagnostics:")
    print(
        selected_v50_summary[
            [
                "strategy_name",
                "total_periods",
                "active_periods",
                "positive_periods",
                "negative_periods",
                "average_profit_factor",
                "median_profit_factor",
                "total_net_profit",
                "worst_period_net_profit",
                "worst_period_drawdown",
                "stability_score",
            ]
        ].to_string(index=False)
    )
    print("")
    print(f"Walk-forward report exported: {WALK_FORWARD_REPORT_PATH}")
    print(f"V50 candidate walk-forward report exported: {candidate_report_path}")
    print("Important: this is backtesting research only, not live trading.")


def _build_strategy_datasets(strategies) -> dict[str, object]:
    strategy_names = {spec.name for spec in strategies}
    if strategy_v50_pine.MTF_STRATEGY_NAME not in strategy_names:
        return {}

    try:
        timeframes = load_xauusd_timeframes(TIMEFRAMES_DIR)
        mtf_dataset = build_v50_mtf_dataset(timeframes)
    except (FileNotFoundError, ValueError) as exc:
        print(f"V50 MTF dataset unavailable, skipping MTF-specific data: {exc}")
        return {}

    print(
        "Loaded V50 MTF dataset: "
        f"{len(mtf_dataset)} M5 rows "
        f"({mtf_dataset['time'].min()} -> {mtf_dataset['time'].max()})"
    )
    print("")
    return {strategy_v50_pine.MTF_STRATEGY_NAME: mtf_dataset}


if __name__ == "__main__":
    main()
