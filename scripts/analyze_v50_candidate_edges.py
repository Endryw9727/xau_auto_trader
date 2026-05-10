"""
Analyze trade-level edges for official V50 technical candidates.

The script reads local Strategy Lab CSV reports and prints raw diagnostics. It
does not promote any strategy automatically.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.trade_level_diagnostics import (
    add_time_buckets,
    build_trade_level_summary,
    find_loss_clusters,
    has_strategy_trade_data,
    summarize_strategy_group,
)
from src.strategy_lab.strategy_v50_candidates import (
    V50_CANDIDATE_COMPARISON_PATH,
    V50_CANDIDATE_EDGES_PATH,
    V50_CANDIDATE_STRATEGY_NAMES,
    export_v50_candidate_comparison,
)


TRADES_BY_STRATEGY_PATH = Path("reports/backtests/trades_by_strategy.csv")
TRADES_PATH = Path("reports/backtests/trades.csv")
STRATEGY_COMPARISON_PATH = Path("reports/strategy_lab/strategy_comparison.csv")


def main() -> None:
    """Print and export V50 candidate edge diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Candidate Edges")
    print("=" * 72)

    trades = load_trade_report()
    if not has_strategy_trade_data(trades):
        print("No strategy-tagged trade report found.")
        print("Run first: python scripts/run_strategy_lab.py --full")
        return

    comparison = _load_optional_csv(STRATEGY_COMPARISON_PATH)
    if comparison is not None:
        comparison_path = export_v50_candidate_comparison(comparison, V50_CANDIDATE_COMPARISON_PATH)
        print(f"V50 candidate comparison exported: {comparison_path}")

    report = build_v50_candidate_edges_report(trades, comparison)
    export_v50_candidate_edges_report(report, V50_CANDIDATE_EDGES_PATH)

    prepared = add_time_buckets(trades)
    for strategy_name in V50_CANDIDATE_STRATEGY_NAMES:
        strategy_trades = prepared[prepared["strategy_name"] == strategy_name].copy()
        if strategy_trades.empty:
            print("")
            print(f"Strategy: {strategy_name}")
            print("(no trades)")
            continue

        print("")
        print(f"Strategy: {strategy_name}")
        _print_overall(strategy_name, report)
        _print_table("LONG vs SHORT", summarize_strategy_group(prepared, strategy_name, "side_label"))
        _print_table("Session performance", summarize_strategy_group(prepared, strategy_name, "session"))
        _print_table("Yearly performance", summarize_strategy_group(prepared, strategy_name, "year"))
        _print_table("Monthly performance", summarize_strategy_group(prepared, strategy_name, "month"))
        _print_table("Worst 20 trades", _select_trade_rows(strategy_trades, ascending=True))
        _print_table("Best 20 trades", _select_trade_rows(strategy_trades, ascending=False))
        _print_table("Consecutive-loss clusters", find_loss_clusters(prepared, strategy_name))

    print("")
    print(f"V50 candidate edges exported: {V50_CANDIDATE_EDGES_PATH}")
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


def build_v50_candidate_edges_report(
    trades: pd.DataFrame,
    comparison: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build a long-form CSV-ready diagnostics report for V50 candidates."""
    prepared = add_time_buckets(trades)
    summary = build_trade_level_summary(prepared, V50_CANDIDATE_STRATEGY_NAMES)
    comparison_lookup = _comparison_lookup(comparison)
    rows = []

    for _, row in summary.iterrows():
        strategy_name = row["strategy_name"]
        comparison_row = comparison_lookup.get(strategy_name, {})
        net_profit = float(comparison_row.get("net_profit", row.get("net_profit", 0.0)))
        max_drawdown = float(comparison_row.get("max_drawdown", 0.0))
        rows.append(
            {
                "strategy_name": strategy_name,
                "section": "overall",
                "group": "ALL",
                "total_trades": int(row["total_trades"]),
                "wins": int(row["wins"]),
                "losses": int(row["losses"]),
                "win_rate": float(row["win_rate"]),
                "profit_factor": float(comparison_row.get("profit_factor", row["profit_factor"])),
                "net_profit": net_profit,
                "max_drawdown": max_drawdown,
                "expectancy": float(comparison_row.get("expectancy", row["average_trade"])),
                "profit_drawdown_ratio": net_profit / max_drawdown if max_drawdown > 0 else 0.0,
                "average_trade": float(row["average_trade"]),
                "max_consecutive_losses": int(row["max_consecutive_losses"]),
            }
        )

        for section, group_column in [
            ("side", "side_label"),
            ("session", "session"),
            ("year", "year"),
            ("month", "month"),
        ]:
            grouped = summarize_strategy_group(prepared, strategy_name, group_column)
            rows.extend(_group_rows(strategy_name, section, grouped))

    return pd.DataFrame(rows)


def export_v50_candidate_edges_report(
    report: pd.DataFrame,
    output_path: str | Path = V50_CANDIDATE_EDGES_PATH,
) -> Path:
    """Export the long-form V50 candidate edge report."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    return output_path


def _group_rows(strategy_name: str, section: str, grouped: pd.DataFrame) -> list[dict]:
    rows = []
    for _, row in grouped.iterrows():
        rows.append(
            {
                "strategy_name": strategy_name,
                "section": section,
                "group": row["group"],
                "total_trades": int(row["total_trades"]),
                "wins": int(row["wins"]),
                "losses": int(row["losses"]),
                "win_rate": float(row["win_rate"]),
                "profit_factor": float(row["profit_factor"]),
                "net_profit": float(row["net_profit"]),
                "max_drawdown": pd.NA,
                "expectancy": pd.NA,
                "profit_drawdown_ratio": pd.NA,
                "average_trade": float(row["average_trade"]),
                "max_consecutive_losses": pd.NA,
            }
        )
    return rows


def _comparison_lookup(comparison: pd.DataFrame | None) -> dict[str, dict]:
    if comparison is None or comparison.empty or "strategy_name" not in comparison.columns:
        return {}

    filtered = comparison[comparison["strategy_name"].isin(V50_CANDIDATE_STRATEGY_NAMES)].copy()
    return filtered.set_index("strategy_name").to_dict(orient="index")


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


def _print_overall(strategy_name: str, report: pd.DataFrame) -> None:
    overall = report[(report["strategy_name"] == strategy_name) & (report["section"] == "overall")]
    if overall.empty:
        return

    columns = [
        "total_trades",
        "win_rate",
        "profit_factor",
        "net_profit",
        "max_drawdown",
        "expectancy",
        "profit_drawdown_ratio",
        "max_consecutive_losses",
    ]
    print(overall[columns].to_string(index=False))


def _print_table(title: str, table: pd.DataFrame) -> None:
    print("")
    print(title)
    if table.empty:
        print("(no data)")
        return
    print(table.to_string(index=False))


def _load_optional_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        print(f"Optional report not found: {path}")
        return None

    print(f"Loaded report: {path}")
    return pd.read_csv(path)


if __name__ == "__main__":
    main()
