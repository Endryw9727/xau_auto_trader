"""
Check controlled paper validation status.

The script can report readiness states, but it keeps allow_live=false and never
activates a strategy automatically.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.paper.paper_monitor import (
    DEFAULT_MONITOR_STRATEGY_NAME,
    DEFAULT_PAPER_MONITOR_SUMMARY_PATH,
    DEFAULT_PAPER_VALIDATION_STATUS_PATH,
    build_monitor_summary,
    build_validation_status,
    export_monitor_summary,
    export_validation_status,
    load_paper_reports,
    load_validation_rules,
)


def main() -> None:
    """Print paper validation status and export CSV report."""
    print("=" * 72)
    print("XAU Auto Trader - Paper Validation Status")
    print("=" * 72)
    print("Mode: paper/research only")

    try:
        reports = load_paper_reports()
        rules = load_validation_rules()
    except FileNotFoundError as exc:
        print(str(exc))
        print("Run first: python scripts/run_paper_simulation.py")
        return

    monitor_summary = build_monitor_summary(reports, strategy_name=DEFAULT_MONITOR_STRATEGY_NAME)
    export_monitor_summary(monitor_summary, DEFAULT_PAPER_MONITOR_SUMMARY_PATH)
    validation = build_validation_status(
        monitor_summary=monitor_summary,
        daily_summary=reports.daily_summary,
        rules=rules,
        strategy_name=DEFAULT_MONITOR_STRATEGY_NAME,
    )
    export_validation_status(validation, DEFAULT_PAPER_VALIDATION_STATUS_PATH)
    row = validation.iloc[0]

    print("")
    print(f"Strategy: {row['strategy_name']}")
    print(f"Validation status: {row['validation_status']}")
    print(f"allow_live: {bool(row['allow_live'])}")
    print(f"Ready for demo: {bool(row['ready_for_demo'])}")
    print(f"Ready for micro-live: {bool(row['ready_for_micro_live'])}")
    print("")
    print("Evidence:")
    print(f"  Paper days: {int(row['paper_days'])}")
    print(f"  Total trades: {int(row['total_trades'])}")
    print(f"  PF total: {float(row['profit_factor_total']):.3f}")
    print(f"  PF last 50: {float(row['profit_factor_last_50']):.3f}")
    print(f"  Max DD: {float(row['max_drawdown_pct']):.2f}%")
    print(f"  Max consecutive losses: {int(row['max_consecutive_losses'])}")
    print(f"  Max trades/day observed: {int(row['max_trades_per_day_observed'])}")

    if row["fail_reasons"]:
        print("")
        print("Not-ready reasons:")
        for reason in str(row["fail_reasons"]).split("; "):
            print(f"  - {reason}")
    if row["observation_reasons"]:
        print("")
        print("Observation reasons:")
        for reason in str(row["observation_reasons"]).split("; "):
            print(f"  - {reason}")

    print("")
    print("Readiness labels:")
    print("  - non pronto: critical thresholds are not met")
    print("  - in osservazione: minimums are met, but warnings remain")
    print("  - pronto per demo: demo observation gates are met")
    print("  - pronto per micro-live: blocked unless allow_live=true in a future approved workflow")
    print("")
    print(f"Monitor summary exported: {DEFAULT_PAPER_MONITOR_SUMMARY_PATH}")
    print(f"Validation status exported: {DEFAULT_PAPER_VALIDATION_STATUS_PATH}")
    print("No strategy was promoted automatically.")


if __name__ == "__main__":
    main()
