"""
Print the current paper-forward status from local CSV reports.

This is a read-only operational report. It does not contact brokers or send
orders.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.paper.paper_forward_engine import build_forward_status


def main() -> None:
    """Print paper-forward status."""
    print("=" * 72)
    print("XAU Auto Trader - Paper Forward Status")
    print("=" * 72)
    print("Mode: local paper only")

    status = build_forward_status()
    decision = "CONTINUE" if status["can_continue_tomorrow"] else "PAUSE"

    print("")
    print(f"Strategy: {status['strategy_name']}")
    print(f"Status: {status['status']}")
    print(f"Equity: {float(status['equity']):.2f} EUR")
    print(f"Open trades: {int(status['open_trades_count'])}")
    print(f"Closed trades: {int(status['closed_trades_count'])}")
    print(f"Total PnL: {float(status['total_pnl']):.2f} EUR")
    print(f"PnL today: {float(status['today_pnl']):.2f} EUR")
    print(f"PF paper-forward: {float(status['profit_factor']):.3f}")
    print(f"DD paper-forward: {float(status['drawdown_pct']):.2f}%")
    print(f"Loss streak current/max: {int(status['loss_streak'])} / {int(status['max_loss_streak'])}")
    print(f"Tomorrow: {decision}")
    if status.get("stop_reason"):
        print(f"Stop reason: {status['stop_reason']}")
    if status.get("warning_reason"):
        print(f"Warning: {status['warning_reason']}")
    print("")
    print("No live trading was enabled. allow_live remains false.")


if __name__ == "__main__":
    main()
