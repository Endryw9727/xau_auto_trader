"""
Analyze why v50_final_balanced_strategy loses.

The script reads simulated backtest trades and exports loss-intelligence CSVs.
It does not activate or promote any strategy.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_feed.market_data import load_csv_data
from src.strategy_lab.strategy_v50_candidates import FINAL_BALANCED_STRATEGY_NAME
from src.strategy_lab.v50_loss_intelligence import (
    DEFAULT_LOSS_BREAKDOWN_PATH,
    DEFAULT_LOSS_CLUSTERS_PATH,
    DEFAULT_LOSS_PATTERN_CANDIDATES_PATH,
    build_loss_breakdown,
    build_loss_clusters,
    build_loss_pattern_candidates,
    export_loss_intelligence_reports,
    load_loss_trade_report,
    max_consecutive_losses,
    prepare_balanced_loss_trades,
)


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Print and export loss-intelligence diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Loss Intelligence")
    print("=" * 72)
    print("Mode: research/backtest only")

    trades = load_loss_trade_report()
    if trades is None:
        print("No strategy-tagged trade report found.")
        print("Run first: python scripts/run_strategy_lab.py --full")
        return

    market_data = _load_market_data()
    prepared = prepare_balanced_loss_trades(trades, FINAL_BALANCED_STRATEGY_NAME)
    if prepared.empty:
        print(f"No trades found for {FINAL_BALANCED_STRATEGY_NAME}.")
        return

    clusters = build_loss_clusters(prepared)
    breakdown = build_loss_breakdown(prepared)
    candidates = build_loss_pattern_candidates(prepared, breakdown, market_data=market_data)
    export_loss_intelligence_reports(
        clusters,
        breakdown,
        candidates,
        DEFAULT_LOSS_CLUSTERS_PATH,
        DEFAULT_LOSS_BREAKDOWN_PATH,
        DEFAULT_LOSS_PATTERN_CANDIDATES_PATH,
    )

    print("")
    print(f"Strategy: {FINAL_BALANCED_STRATEGY_NAME}")
    print(f"Total trades: {len(prepared)}")
    print(f"Max consecutive losses: {max_consecutive_losses(prepared)}")

    _print_worst_section("Worst hours", breakdown, "hour")
    _print_worst_section("Worst weekdays", breakdown, "weekday")
    _print_worst_section("Worst months", breakdown, "month")
    _print_worst_section("Worst sessions", breakdown, "session")
    _print_worst_section("Worst session + side", breakdown, "session_side")
    _print_worst_section("Worst score buckets", breakdown, "score_bucket")
    _print_worst_section("Worst bars-in-trade buckets", breakdown, "bars_in_trade_bucket")

    print("")
    print("Loss clusters:")
    _print_table(clusters.sort_values(["loss_count", "net_loss"], ascending=[False, True]).head(20))

    print("")
    print("Pattern candidates:")
    _print_table(candidates.head(20))

    print("")
    print(f"Loss clusters exported: {DEFAULT_LOSS_CLUSTERS_PATH}")
    print(f"Loss breakdown exported: {DEFAULT_LOSS_BREAKDOWN_PATH}")
    print(f"Loss pattern candidates exported: {DEFAULT_LOSS_PATTERN_CANDIDATES_PATH}")
    print("No strategy was promoted automatically.")


def _load_market_data() -> pd.DataFrame | None:
    if not RAW_DATA_PATH.exists():
        return None
    return load_csv_data(RAW_DATA_PATH)


def _print_worst_section(title: str, breakdown: pd.DataFrame, pattern_type: str) -> None:
    print("")
    print(title)
    section = breakdown[breakdown["pattern_type"] == pattern_type].copy()
    _print_table(section.sort_values(["net_profit", "total_trades"], ascending=[True, False]).head(10))


def _print_table(table: pd.DataFrame) -> None:
    if table.empty:
        print("(no data)")
        return
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
