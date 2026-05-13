"""
Select NORMAL / DEFENSIVE / PAUSE paper mode.

The selection is advisory only. It does not change configuration, place orders,
or promote anything to live trading.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.paper.paper_degradation import (
    DEFAULT_DEFENSIVE_MODE_PATH,
    build_defensive_mode_report,
    export_dataframe,
    load_or_build_monitor_summary,
)
from src.paper.paper_monitor import load_paper_reports


def main() -> None:
    """Print and export defensive paper mode recommendation."""
    print("=" * 72)
    print("XAU Auto Trader - Defensive Paper Mode")
    print("=" * 72)
    print("Mode: paper/research advisory only")

    try:
        reports = load_paper_reports()
    except FileNotFoundError as exc:
        print(str(exc))
        print("Run first: python scripts/run_paper_simulation.py")
        return

    monitor_summary = load_or_build_monitor_summary(reports)
    defensive = build_defensive_mode_report(monitor_summary)
    export_dataframe(defensive, DEFAULT_DEFENSIVE_MODE_PATH)
    row = defensive.iloc[0]

    print("")
    print(f"Strategy: {row['strategy_name']}")
    print(f"Recommended mode: {row['recommended_mode']}")
    print(f"Recommended strategy: {row['recommended_strategy']}")
    print(f"Paper trade allowed: {bool(row['paper_trade_allowed'])}")
    print(f"allow_live: {bool(row['allow_live'])}")
    print("")
    print("Inputs:")
    print(f"  PF last 50: {float(row['profit_factor_last_50']):.3f}")
    print(f"  Max DD: {float(row['max_drawdown_pct']):.2f}%")
    print(f"  Current loss streak: {int(row['current_loss_streak'])}")
    print(f"  Max loss streak: {int(row['max_loss_streak'])}")
    print("")
    print("Reason:")
    print(f"  {row['reason']}")
    print("")
    print(f"Defensive mode exported: {DEFAULT_DEFENSIVE_MODE_PATH}")
    print("No configuration was changed and no strategy was promoted automatically.")


if __name__ == "__main__":
    main()
