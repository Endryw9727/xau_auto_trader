"""
Analyze daily trade coverage for final V50 candidates.

This script reads local backtest CSV reports. It is research-only and does not
execute trades.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_feed.market_data import load_csv_data
from src.strategy_lab.strategy_v50_candidates import FINAL_CANDIDATE_STRATEGY_NAMES
from src.strategy_lab.v50_daily_coverage import (
    DEFAULT_DAILY_BREAKDOWN_PATH,
    DEFAULT_DAILY_COVERAGE_PATH,
    best_days,
    build_daily_breakdown,
    build_daily_coverage_report,
    export_daily_coverage_reports,
    load_strategy_trade_report,
    loss_cluster_days,
    no_trade_volatile_days,
    worst_days,
)


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Print and export daily coverage diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Daily Coverage")
    print("=" * 72)
    print("Mode: research/backtest only")

    trades = load_strategy_trade_report()
    if trades is None:
        print("No strategy-tagged trade report found.")
        print("Run first: python scripts/run_strategy_lab.py --full")
        return

    market_data = _load_market_data()
    breakdown = build_daily_breakdown(
        trades,
        strategy_names=FINAL_CANDIDATE_STRATEGY_NAMES,
        market_data=market_data,
    )
    coverage = build_daily_coverage_report(breakdown)
    coverage_path, breakdown_path = export_daily_coverage_reports(
        coverage,
        breakdown,
        DEFAULT_DAILY_COVERAGE_PATH,
        DEFAULT_DAILY_BREAKDOWN_PATH,
    )

    print("")
    print("Daily coverage summary:")
    print(coverage.to_string(index=False))

    for strategy_name in FINAL_CANDIDATE_STRATEGY_NAMES:
        print("")
        print(f"Strategy: {strategy_name}")
        _print_table("Worst days", worst_days(breakdown, strategy_name, limit=10))
        _print_table("Best days", best_days(breakdown, strategy_name, limit=10))
        _print_table("Days with loss clusters", loss_cluster_days(breakdown, strategy_name, min_consecutive_losses=2).head(10))
        _print_table("No-trade volatile days", no_trade_volatile_days(breakdown, strategy_name, limit=10))

    print("")
    print(f"Daily coverage exported: {coverage_path}")
    print(f"Daily breakdown exported: {breakdown_path}")
    print("No strategy was promoted automatically.")


def _load_market_data() -> pd.DataFrame | None:
    if not RAW_DATA_PATH.exists():
        print(f"Optional market data not found: {RAW_DATA_PATH}")
        return None
    return load_csv_data(RAW_DATA_PATH)


def _print_table(title: str, table: pd.DataFrame) -> None:
    print("")
    print(title)
    if table.empty:
        print("(no data)")
        return
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
