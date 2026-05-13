"""
Run one controlled paper-forward cycle.

The script reads local OHLCV data, updates simulated paper trades, evaluates
the latest closed candle, and records paper-only decisions. It never sends real
orders.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.paper_preflight_check import run_preflight_checks
from src.data_feed.market_data import load_csv_data
from src.paper.paper_forward_engine import run_paper_forward_once


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Run one paper-forward evaluation and print a compact report."""
    print("=" * 72)
    print("XAU Auto Trader - Paper Forward Once")
    print("=" * 72)
    print("Mode: local paper only. No real orders are possible.")

    checks = run_preflight_checks()
    failed = [item for item in checks if not item["passed"]]
    if failed:
        print("")
        print("Preflight status: FAIL")
        for item in failed:
            print(f"  - {item['name']}: {item['detail']}")
        print("Decision: STOP")
        print("Next action: resolve preflight failures before paper-forward.")
        return

    if not RAW_DATA_PATH.exists():
        print(f"CSV file not found: {RAW_DATA_PATH}")
        print("Decision: STOP")
        return

    market_data = load_csv_data(RAW_DATA_PATH)
    result = run_paper_forward_once(market_data)

    print("")
    print(f"System status: {result.status}")
    print(f"Strategy: {result.strategy_name}")
    print(f"Signal: {result.decision}")
    print(f"Reason: {result.reason}")
    print(f"Paper equity: {result.equity:.2f} EUR")
    print(f"Paper DD: {result.drawdown_pct:.2f}%")
    print(f"Open paper trades: {result.open_trades}")
    print(f"Daily loss: {result.daily_loss_pct:.2f}%")
    print(f"Next action: {result.next_action}")
    if result.trade_id:
        print(f"Paper trade id: {result.trade_id}")
    print("")
    print("No live trading was enabled. allow_live remains false.")


if __name__ == "__main__":
    main()
