"""
Create a diagnostic report for selected Strategy Lab candidates.

The script reads existing CSV reports and writes a research-only summary.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy_lab.strategy_diagnostics import (
    DEFAULT_DIAGNOSTIC_STRATEGIES,
    STRATEGY_DIAGNOSTICS_REPORT_PATH,
    build_strategy_diagnostics,
    export_strategy_diagnostics,
)
from src.analysis.trade_level_diagnostics import (
    add_time_buckets,
    build_trade_level_summary,
    has_strategy_trade_data,
    summarize_strategy_group,
)


WALK_FORWARD_PATH = Path("reports/strategy_lab/walk_forward_analysis.csv")
STRATEGY_COMPARISON_PATH = Path("reports/strategy_lab/strategy_comparison.csv")
TRADES_PATH = Path("reports/backtests/trades.csv")
TRADES_BY_STRATEGY_PATH = Path("reports/backtests/trades_by_strategy.csv")


def main() -> None:
    """Build and print the diagnostics report."""
    print("=" * 72)
    print("XAU Auto Trader - Strategy Diagnostics")
    print("=" * 72)

    if not WALK_FORWARD_PATH.exists():
        print(f"Missing walk-forward report: {WALK_FORWARD_PATH}")
        print("Run first: python scripts/run_walk_forward_analysis.py --period quarter")
        return

    walk_forward = pd.read_csv(WALK_FORWARD_PATH)
    strategy_comparison = _load_optional_csv(STRATEGY_COMPARISON_PATH)
    trades = _load_trade_report()

    diagnostics = build_strategy_diagnostics(
        walk_forward=walk_forward,
        strategy_comparison=strategy_comparison,
        strategy_names=DEFAULT_DIAGNOSTIC_STRATEGIES,
    )
    output_path = export_strategy_diagnostics(
        diagnostics,
        STRATEGY_DIAGNOSTICS_REPORT_PATH,
    )

    print("")
    print("Target strategies:")
    for strategy_name in DEFAULT_DIAGNOSTIC_STRATEGIES:
        print(f"- {strategy_name}")

    print("")
    _print_trade_csv_note(trades)
    _print_trade_level_analysis(trades)

    print("")
    print("Diagnostics by stability_score:")
    print(
        diagnostics[
            [
                "strategy_name",
                "total_periods",
                "active_periods",
                "no_trade_periods",
                "positive_periods",
                "negative_periods",
                "total_trades",
                "avg_trades_per_active_period",
                "average_profit_factor",
                "median_profit_factor",
                "total_net_profit",
                "worst_period_net_profit",
                "worst_period_drawdown",
                "profit_drawdown_ratio",
                "stability_score",
            ]
        ].to_string(index=False)
    )

    print("")
    print("Score components:")
    print(
        diagnostics[
            [
                "strategy_name",
                "active_coverage",
                "positive_active_ratio",
                "normalized_profit_drawdown_ratio",
                "coverage_penalty",
                "profit_factor_penalty",
                "drawdown_penalty",
                "stability_score",
            ]
        ].to_string(index=False)
    )

    print("")
    print(f"Diagnostics exported: {output_path}")
    print("No strategy was promoted automatically.")


def _load_optional_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        print(f"Optional report not found: {path}")
        return None

    print(f"Loaded report: {path}")
    return pd.read_csv(path)


def _load_trade_report() -> pd.DataFrame | None:
    by_strategy = _load_optional_csv(TRADES_BY_STRATEGY_PATH)
    if has_strategy_trade_data(by_strategy):
        return by_strategy

    trades = _load_optional_csv(TRADES_PATH)
    if has_strategy_trade_data(trades):
        return trades

    return trades if trades is not None else by_strategy


def _print_trade_csv_note(trades: pd.DataFrame | None) -> None:
    if trades is None:
        print("Trade-level CSV not found; diagnostics use walk-forward and comparison reports.")
        return

    if "strategy_name" not in trades.columns:
        print(
            "Trade-level CSV found, but it has no strategy_name column; "
            "per-strategy diagnostics use walk-forward and comparison reports."
        )
        return

    print("Trade-level CSV includes strategy_name and is available for deeper manual checks.")


def _print_trade_level_analysis(trades: pd.DataFrame | None) -> None:
    if not has_strategy_trade_data(trades):
        return

    summary = build_trade_level_summary(trades, DEFAULT_DIAGNOSTIC_STRATEGIES)
    if summary.empty:
        return

    print("")
    print("Trade-level summary:")
    print(summary.to_string(index=False))

    prepared = add_time_buckets(trades)
    for strategy_name in DEFAULT_DIAGNOSTIC_STRATEGIES:
        strategy_trades = prepared[prepared["strategy_name"] == strategy_name]
        if strategy_trades.empty:
            continue

        print("")
        print(f"Trade-level breakdown for {strategy_name}:")
        for label, group_column in [
            ("pnl_by_side", "side_label"),
            ("pnl_by_session", "session"),
            ("pnl_by_year", "year"),
            ("pnl_by_month", "month"),
        ]:
            grouped = summarize_strategy_group(prepared, strategy_name, group_column)
            if grouped.empty:
                continue
            print(label)
            print(grouped.to_string(index=False))


if __name__ == "__main__":
    main()
