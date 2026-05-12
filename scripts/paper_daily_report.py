"""
Print daily paper-monitoring report.

This is a paper/research monitor only. It reads local CSV reports and never
places orders.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.paper.paper_monitor import (
    DEFAULT_MONITOR_STRATEGY_NAME,
    DEFAULT_PAPER_MONITOR_SUMMARY_PATH,
    build_monitor_summary,
    export_monitor_summary,
    load_paper_reports,
)


def main() -> None:
    """Build and print the daily paper status report."""
    print("=" * 72)
    print("XAU Auto Trader - Paper Daily Report")
    print("=" * 72)
    print("Mode: paper/research only")

    try:
        reports = load_paper_reports()
    except FileNotFoundError as exc:
        print(str(exc))
        print("Run first: python scripts/run_paper_simulation.py")
        return

    summary = build_monitor_summary(reports, strategy_name=DEFAULT_MONITOR_STRATEGY_NAME)
    export_monitor_summary(summary, DEFAULT_PAPER_MONITOR_SUMMARY_PATH)
    row = summary.iloc[0]

    print("")
    print(f"Strategy: {row['strategy_name']}")
    print(f"Report as of: {row['report_as_of']}")
    print(f"Status: {row['status']}")
    print("")
    print("Equity and risk:")
    print(f"  Equity: {float(row['equity_current']):.2f} EUR")
    print(f"  Total P/L: {float(row['total_profit_loss']):.2f} EUR")
    print(
        "  Drawdown current/max: "
        f"{float(row['current_drawdown_pct']):.2f}% / {float(row['max_drawdown_pct']):.2f}%"
    )
    print("")
    print("Performance:")
    print(f"  PF total: {float(row['profit_factor_total']):.3f}")
    print(f"  PF last 30 trades: {float(row['profit_factor_last_30']):.3f}")
    print(f"  PF last 50 trades: {float(row['profit_factor_last_50']):.3f}")
    print(f"  Win rate total / last 30: {float(row['win_rate_total']):.2f}% / {float(row['win_rate_last_30']):.2f}%")
    print("")
    print("Activity:")
    print(f"  Total trades: {int(row['total_trades'])}")
    print(f"  Trades today/week/month: {int(row['trades_today'])} / {int(row['trades_week'])} / {int(row['trades_month'])}")
    print(f"  Current no-trade days: {int(row['current_no_trade_days'])}")
    print("")
    print("Loss controls:")
    print(f"  Max consecutive losses: {int(row['max_consecutive_losses'])}")
    print(f"  Current consecutive losses: {int(row['current_consecutive_losses'])}")
    print(f"  Daily loss current: {float(row['daily_loss_current']):.2f} EUR ({float(row['daily_loss_current_pct']):.2f}%)")
    print(f"  Weekly loss current: {float(row['weekly_loss_current']):.2f} EUR ({float(row['weekly_loss_current_pct']):.2f}%)")
    print("")
    print("Last trade:")
    print(f"  Time: {row['last_trade_time']}")
    print(f"  Session: {row['last_session']}")
    print(f"  Result: {row['last_result']}")
    print(f"  Reason: {row['last_entry_reason']}")

    if row["stop_reasons"]:
        print("")
        print("STOP reasons:")
        for reason in str(row["stop_reasons"]).split("; "):
            print(f"  - {reason}")
    if row["warning_reasons"]:
        print("")
        print("WARNING reasons:")
        for reason in str(row["warning_reasons"]).split("; "):
            print(f"  - {reason}")

    print("")
    if row["status"] == "OK":
        print("Paper limits: inside monitored limits.")
    elif row["status"] == "WARNING":
        print("Paper limits: warning state, continue only with stricter observation.")
    else:
        print("Paper limits: STOP state, pause the paper strategy and review.")
    print(f"Monitor summary exported: {DEFAULT_PAPER_MONITOR_SUMMARY_PATH}")
    print("No live trading was enabled.")


if __name__ == "__main__":
    main()
