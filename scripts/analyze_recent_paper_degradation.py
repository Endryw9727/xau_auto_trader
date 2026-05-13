"""
Analyze recent paper degradation for the main V50 paper candidate.

This reads local paper CSV reports only. It does not modify strategy logic or
enable live trading.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.paper.paper_degradation import (
    DEFAULT_MAIN_VS_HIGH_MARGIN_RECENT_PATH,
    DEFAULT_RECENT_DEGRADATION_BREAKDOWN_PATH,
    DEFAULT_RECENT_DEGRADATION_PATH,
    build_main_vs_high_margin_recent_report,
    build_recent_degradation_reports,
    export_dataframe,
)
from src.paper.paper_monitor import DEFAULT_MONITOR_STRATEGY_NAME, load_paper_reports


DISPLAY_COLUMNS = [
    "window_label",
    "total_trades",
    "win_rate",
    "profit_factor",
    "net_profit",
    "average_trade",
    "max_drawdown",
    "max_consecutive_losses",
    "worst_session",
    "worst_hour",
    "worst_side",
    "worst_score_bucket",
    "worst_day_of_week",
]


def main() -> None:
    """Build recent degradation and main-vs-high-margin reports."""
    print("=" * 72)
    print("XAU Auto Trader - Recent Paper Degradation")
    print("=" * 72)
    print("Mode: paper/research only")

    try:
        reports = load_paper_reports()
    except FileNotFoundError as exc:
        print(str(exc))
        print("Run first: python scripts/run_paper_simulation.py")
        return

    degradation, breakdown = build_recent_degradation_reports(
        reports,
        strategy_name=DEFAULT_MONITOR_STRATEGY_NAME,
    )
    main_vs = build_main_vs_high_margin_recent_report(reports)
    export_dataframe(degradation, DEFAULT_RECENT_DEGRADATION_PATH)
    export_dataframe(breakdown, DEFAULT_RECENT_DEGRADATION_BREAKDOWN_PATH)
    export_dataframe(main_vs, DEFAULT_MAIN_VS_HIGH_MARGIN_RECENT_PATH)

    print("")
    print(f"Strategy: {DEFAULT_MONITOR_STRATEGY_NAME}")
    print("Recent windows:")
    print(degradation[DISPLAY_COLUMNS].to_string(index=False))
    print("")
    print("Main vs high-margin:")
    print(
        main_vs[
            [
                "strategy_name",
                "profit_factor_total",
                "profit_factor_last_30",
                "profit_factor_last_50",
                "profit_factor_last_year",
                "max_drawdown_pct",
                "max_loss_streak",
                "trades_per_day",
                "ending_equity",
                "avoids_recent_degradation_vs_main",
                "reduces_loss_streak_vs_main",
            ]
        ].to_string(index=False)
    )
    print("")
    print(f"Recent degradation exported: {DEFAULT_RECENT_DEGRADATION_PATH}")
    print(f"Breakdown exported: {DEFAULT_RECENT_DEGRADATION_BREAKDOWN_PATH}")
    print(f"Main-vs-high-margin exported: {DEFAULT_MAIN_VS_HIGH_MARGIN_RECENT_PATH}")
    print("No strategy was changed or promoted automatically.")


if __name__ == "__main__":
    main()
