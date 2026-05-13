"""
End-of-day paper report for the frozen high-margin paper candidate.

This script reads local paper CSV reports only and does not enable live trading.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.paper.paper_candidate import load_paper_candidate_config
from src.paper.paper_monitor import build_monitor_summary, load_paper_reports


def main() -> None:
    """Print end-of-day paper diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - Paper End Of Day Report")
    print("=" * 72)
    print("Mode: paper/research only")

    try:
        candidate = load_paper_candidate_config()
        reports = load_paper_reports()
    except FileNotFoundError as exc:
        print(str(exc))
        print("Run first: python scripts/run_paper_simulation.py")
        return

    summary = build_monitor_summary(reports, strategy_name=candidate.paper_main_strategy)
    row = summary.iloc[0]
    trades_today, day_pnl = todays_trades_and_pnl(reports.trades, candidate.paper_main_strategy, str(row["report_as_of"]))
    decision, reasons = continuation_decision(row, candidate)

    print("")
    print(f"Paper main strategy: {candidate.paper_main_strategy}")
    print(f"Report date: {row['report_as_of']}")
    print(f"Trades today: {trades_today}")
    print(f"PnL day: {day_pnl:.2f} EUR")
    print(f"Equity current: {float(row['equity_current']):.2f} EUR")
    print(f"DD current/max: {float(row['current_drawdown_pct']):.2f}% / {float(row['max_drawdown_pct']):.2f}%")
    print(f"PF total: {float(row['profit_factor_total']):.3f}")
    print(f"PF last 30/50: {float(row['profit_factor_last_30']):.3f} / {float(row['profit_factor_last_50']):.3f}")
    print(f"Loss streak current/max: {int(row['current_consecutive_losses'])} / {int(row['max_consecutive_losses'])}")
    print("")
    print(f"Tomorrow decision: {decision}")
    for reason in reasons:
        print(f"  - {reason}")
    print("")
    print("No live trading was enabled. allow_live remains false.")


def todays_trades_and_pnl(trades: pd.DataFrame, strategy_name: str, report_date: str) -> tuple[int, float]:
    """Return number of trades and PnL for report date."""
    if trades.empty:
        return 0, 0.0
    result = trades.copy()
    result = result[result["strategy_name"] == strategy_name]
    result["entry_time"] = pd.to_datetime(result["entry_time"], errors="coerce")
    report_day = pd.to_datetime(report_date, errors="coerce")
    if pd.isna(report_day):
        return 0, 0.0
    day = result[result["entry_time"].dt.normalize() == report_day.normalize()]
    pnl = pd.to_numeric(day.get("pnl_eur", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    return int(len(day)), float(pnl.sum())


def continuation_decision(row: pd.Series, candidate_config) -> tuple[str, list[str]]:
    """Return CONTINUE, CAUTION, PAUSE, or EMERGENCY_RESEARCH."""
    pf_50 = float(row.get("profit_factor_last_50", 0.0))
    max_dd = float(row.get("max_drawdown_pct", 0.0))
    daily_loss_pct = float(row.get("daily_loss_current_pct", 0.0))
    weekly_loss_pct = float(row.get("weekly_loss_current_pct", 0.0))
    status = str(row.get("status", "OK"))
    reasons = []

    if (
        status == "STOP"
        or pf_50 < candidate_config.min_recent_50_pf_stop
        or max_dd >= candidate_config.stop_drawdown_pct
        or daily_loss_pct > candidate_config.max_daily_loss_pct
        or weekly_loss_pct > candidate_config.max_weekly_loss_pct
    ):
        if pf_50 < candidate_config.min_recent_50_pf_stop:
            reasons.append(f"PF last 50 {pf_50:.2f} below stop {candidate_config.min_recent_50_pf_stop:.2f}")
        if max_dd >= candidate_config.stop_drawdown_pct:
            reasons.append(f"drawdown {max_dd:.2f}% at/above stop {candidate_config.stop_drawdown_pct:.2f}%")
        if daily_loss_pct > candidate_config.max_daily_loss_pct:
            reasons.append(f"daily loss {daily_loss_pct:.2f}% above {candidate_config.max_daily_loss_pct:.2f}%")
        if weekly_loss_pct > candidate_config.max_weekly_loss_pct:
            reasons.append(f"weekly loss {weekly_loss_pct:.2f}% above {candidate_config.max_weekly_loss_pct:.2f}%")
        return "PAUSE", reasons or ["monitor status is STOP"]

    if max_dd >= candidate_config.warning_drawdown_pct or pf_50 < candidate_config.min_recent_50_pf_warning:
        if max_dd >= candidate_config.warning_drawdown_pct:
            reasons.append(f"drawdown {max_dd:.2f}% above warning {candidate_config.warning_drawdown_pct:.2f}%")
        if pf_50 < candidate_config.min_recent_50_pf_warning:
            reasons.append(f"PF last 50 {pf_50:.2f} below warning {candidate_config.min_recent_50_pf_warning:.2f}")
        return "EMERGENCY_RESEARCH", reasons + [f"review {candidate_config.emergency_mode}, no automatic switch"]

    if status == "WARNING":
        return "CAUTION", ["monitor status is WARNING"]

    return "CONTINUE", ["inside paper limits for next session"]


if __name__ == "__main__":
    main()
