"""
Trade-level edge diagnostics for v50_pine_technical_strategy.

The script reads exported backtest trade reports and prints raw numerical
observations only.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.trade_level_diagnostics import (
    add_time_buckets,
    build_numeric_observations,
    find_loss_clusters,
    has_strategy_trade_data,
    summarize_strategy_group,
)


TARGET_STRATEGY = "v50_pine_technical_strategy"
TRADES_BY_STRATEGY_PATH = Path("reports/backtests/trades_by_strategy.csv")
TRADES_PATH = Path("reports/backtests/trades.csv")


def main() -> None:
    """Print trade-level diagnostics for the V50 technical candidate."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Trade Edges")
    print("=" * 72)

    trades = load_trade_report()
    if not has_strategy_trade_data(trades):
        print("No strategy-tagged trade report found.")
        print("Run first: python scripts/run_strategy_lab.py --full")
        return

    report = build_v50_edge_report(trades)
    if report["trades"].empty:
        print(f"No trades found for {TARGET_STRATEGY}.")
        return

    print(f"Strategy: {TARGET_STRATEGY}")
    print(f"Trades analyzed: {len(report['trades'])}")

    _print_table("Performance LONG vs SHORT", report["by_side"])
    _print_table("Performance by session", report["by_session"])
    _print_table("Performance by year", report["by_year"])
    _print_table("Performance by month", report["by_month"])
    _print_table("Worst 20 trades", report["worst_trades"])
    _print_table("Best 20 trades", report["best_trades"])
    _print_table("Consecutive-loss clusters", report["loss_clusters"])

    print("")
    print("Raw numerical observations:")
    for observation in report["observations"]:
        print(f"- {observation}")

    print("")
    print("No strategy was promoted automatically.")


def load_trade_report() -> pd.DataFrame | None:
    """Load the best available strategy-tagged trade report."""
    for path in [TRADES_BY_STRATEGY_PATH, TRADES_PATH]:
        if not path.exists():
            continue

        trades = pd.read_csv(path)
        if has_strategy_trade_data(trades):
            print(f"Loaded trade report: {path}")
            return trades

    return None


def build_v50_edge_report(trades: pd.DataFrame) -> dict[str, pd.DataFrame | list[str]]:
    """Build all V50 trade edge tables from a trade DataFrame."""
    prepared = add_time_buckets(trades)
    strategy_trades = prepared[prepared["strategy_name"] == TARGET_STRATEGY].copy()

    if not strategy_trades.empty and "entry_time" in strategy_trades.columns:
        strategy_trades = strategy_trades.sort_values("entry_time")

    return {
        "trades": strategy_trades,
        "by_side": summarize_strategy_group(prepared, TARGET_STRATEGY, "side_label"),
        "by_session": summarize_strategy_group(prepared, TARGET_STRATEGY, "session"),
        "by_year": summarize_strategy_group(prepared, TARGET_STRATEGY, "year"),
        "by_month": summarize_strategy_group(prepared, TARGET_STRATEGY, "month"),
        "worst_trades": _select_trade_rows(strategy_trades, ascending=True),
        "best_trades": _select_trade_rows(strategy_trades, ascending=False),
        "loss_clusters": find_loss_clusters(prepared, TARGET_STRATEGY),
        "observations": build_numeric_observations(prepared, TARGET_STRATEGY),
    }


def _select_trade_rows(trades: pd.DataFrame, ascending: bool) -> pd.DataFrame:
    if trades.empty or "pnl" not in trades.columns:
        return pd.DataFrame()

    columns = [
        "entry_time",
        "exit_time",
        "side_label",
        "session",
        "pnl",
        "bars_in_trade",
        "score_long",
        "score_short",
        "signal_reason",
    ]
    available_columns = [column for column in columns if column in trades.columns]
    return trades.sort_values("pnl", ascending=ascending)[available_columns].head(20).reset_index(drop=True)


def _print_table(title: str, table: pd.DataFrame) -> None:
    print("")
    print(title)
    if table.empty:
        print("(no data)")
        return
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
