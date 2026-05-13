"""
Analyze rolling paper stability for the main V50 paper candidate.

This is diagnostic only and does not change strategy logic.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.paper.paper_degradation import (
    DEFAULT_ROLLING_STABILITY_PATH,
    DEFAULT_WORST_ROLLING_WINDOWS_PATH,
    build_rolling_stability_reports,
    export_dataframe,
)
from src.paper.paper_monitor import DEFAULT_MONITOR_STRATEGY_NAME, load_paper_reports


def main() -> None:
    """Build rolling stability and worst-window reports."""
    print("=" * 72)
    print("XAU Auto Trader - Rolling Paper Stability")
    print("=" * 72)
    print("Mode: paper/research only")

    try:
        reports = load_paper_reports()
    except FileNotFoundError as exc:
        print(str(exc))
        print("Run first: python scripts/run_paper_simulation.py")
        return

    rolling, worst = build_rolling_stability_reports(
        reports,
        strategy_name=DEFAULT_MONITOR_STRATEGY_NAME,
    )
    export_dataframe(rolling, DEFAULT_ROLLING_STABILITY_PATH)
    export_dataframe(worst, DEFAULT_WORST_ROLLING_WINDOWS_PATH)

    print("")
    print(f"Strategy: {DEFAULT_MONITOR_STRATEGY_NAME}")
    print("Worst rolling windows:")
    print(
        worst[
            [
                "window_size",
                "start_trade_number",
                "end_trade_number",
                "start_time",
                "end_time",
                "rolling_profit_factor",
                "rolling_net_profit",
                "rolling_max_drawdown",
                "rolling_consecutive_losses",
                "degradation_start_time",
                "worst_session",
                "worst_hour",
                "worst_side",
            ]
        ].to_string(index=False)
    )
    print("")
    print(f"Rolling stability exported: {DEFAULT_ROLLING_STABILITY_PATH}")
    print(f"Worst windows exported: {DEFAULT_WORST_ROLLING_WINDOWS_PATH}")
    print("No strategy was changed or promoted automatically.")


if __name__ == "__main__":
    main()
