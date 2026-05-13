"""
Run dynamic NORMAL / DEFENSIVE / PAUSE paper-mode simulation.

This is local research/backtest work only. It reads paper CSV reports and never
places live orders.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.paper.defensive_mode_engine import (
    DEFAULT_DYNAMIC_DEFENSIVE_AUDIT_PATH,
    DEFAULT_DYNAMIC_DEFENSIVE_SUMMARY_PATH,
    DEFAULT_DYNAMIC_DEFENSIVE_TIMELINE_PATH,
    export_dynamic_defensive_reports,
    run_dynamic_defensive_paper_simulation,
)
from src.paper.paper_engine import load_paper_trading_config
from src.paper.paper_monitor import load_paper_reports


DISPLAY_COLUMNS = [
    "variant_name",
    "total_trades",
    "trades_per_day",
    "profit_factor_net",
    "ending_equity",
    "max_drawdown_pct",
    "max_drawdown_eur",
    "win_rate",
    "expectancy",
    "max_consecutive_losses",
    "profit_factor_last_30",
    "profit_factor_last_50",
    "profit_factor_last_100",
    "months_positive",
    "months_negative",
    "worst_month",
    "days_in_normal",
    "days_in_defensive",
    "days_in_pause",
    "trades_avoided_by_defensive",
    "trades_avoided_by_pause",
]


def main() -> None:
    """Run and export dynamic defensive paper simulation."""
    print("=" * 72)
    print("XAU Auto Trader - Dynamic Defensive Paper Simulation")
    print("=" * 72)
    print("Mode: paper/research/backtest only")

    try:
        config = load_paper_trading_config()
        reports = load_paper_reports()
    except FileNotFoundError as exc:
        print(str(exc))
        print("Run first: python scripts/run_paper_simulation.py")
        return

    summary, timeline, audit = run_dynamic_defensive_paper_simulation(reports, config)
    export_dynamic_defensive_reports(
        summary,
        timeline,
        audit,
        summary_path=DEFAULT_DYNAMIC_DEFENSIVE_SUMMARY_PATH,
        timeline_path=DEFAULT_DYNAMIC_DEFENSIVE_TIMELINE_PATH,
        audit_path=DEFAULT_DYNAMIC_DEFENSIVE_AUDIT_PATH,
    )

    print("")
    print("Simulation summary:")
    print(summary[DISPLAY_COLUMNS].to_string(index=False))
    print("")
    print(f"Summary exported: {DEFAULT_DYNAMIC_DEFENSIVE_SUMMARY_PATH}")
    print(f"Timeline exported: {DEFAULT_DYNAMIC_DEFENSIVE_TIMELINE_PATH}")
    print(f"Trade audit exported: {DEFAULT_DYNAMIC_DEFENSIVE_AUDIT_PATH}")
    print("allow_live remains false. No strategy was promoted automatically.")


if __name__ == "__main__":
    main()
