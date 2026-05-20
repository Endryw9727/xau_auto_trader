"""Run one isolated MT5 demo execution attempt or dry-run simulation."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_feed.market_data import load_csv_data
from src.execution.mt5_demo_executor import DemoOrderRequest, MT5DemoExecutor, load_demo_execution_config
from src.paper.paper_engine import load_paper_trading_config
from src.paper.paper_forward_engine import generate_high_margin_candidate
from src.strategy.rules import StrategyConfig


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Run demo execution dry-run or gated demo execution."""
    args = parse_args()
    dry_run = not args.execute_demo

    print("=" * 72)
    print("XAU Auto Trader - Demo Execution Once")
    print("=" * 72)
    print("Mode: DRY_RUN" if dry_run else "Mode: EXECUTE_DEMO")

    config = load_demo_execution_config()
    print(f"Symbol: {config.symbol}")
    print(f"allow_demo_execution: {config.allow_demo_execution}")
    print(f"allow_real_live: {config.allow_real_live}")
    print(f"execution_enabled: {config.execution_enabled}")

    candidate = build_demo_signal_request(config)
    if candidate is None:
        print("Signal: NO_TRADE")
        print("Reason: no executable closed-candle signal from frozen high-margin candidate")
        print("No demo request was submitted.")
        return

    executor = MT5DemoExecutor(config)
    result = executor.submit_demo_market_order(candidate, dry_run=dry_run, persist=not dry_run)

    print(f"Signal id: {result.signal_id}")
    print(f"Side: {candidate.side}")
    print(f"Volume: {candidate.volume}")
    print(f"SL: {candidate.stop_loss}")
    print(f"TP: {candidate.take_profit}")
    print(f"Status: {result.status}")
    print(f"Accepted: {result.accepted}")
    print(f"Reason: {result.reason}")
    print("No real live execution is enabled.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Simulate locally without submitting to MT5.")
    mode.add_argument("--execute-demo", action="store_true", help="Submit only to verified MT5 demo if all gates pass.")
    return parser.parse_args()


def build_demo_signal_request(config) -> DemoOrderRequest | None:
    """Build a demo request from the latest closed local candle signal."""
    if not RAW_DATA_PATH.exists():
        return None
    market_data = load_csv_data(RAW_DATA_PATH)
    if market_data.empty:
        return None
    paper_config = load_paper_trading_config()
    signal_candidate = generate_high_margin_candidate(
        market_data,
        StrategyConfig(),
        paper_config,
        equity=float(paper_config.initial_equity),
    )
    signal = signal_candidate.signal
    if not signal_candidate.allowed or signal.side not in {"BUY", "SELL"}:
        return None
    candle_time = pd.Timestamp(market_data.index[-1]).strftime("%Y%m%d%H%M")
    signal_id = f"demo_{candle_time}_{signal.side}"
    return DemoOrderRequest(
        signal_id=signal_id,
        side=signal.side,
        volume=config.min_lot,
        stop_loss=float(signal.stop_loss) if signal.stop_loss is not None else None,
        take_profit=float(signal.take_profit) if signal.take_profit is not None else None,
        expected_price=float(signal.entry_price) if signal.entry_price is not None else None,
        comment="dry_run" if config.execution_enabled is False else "demo",
    )


if __name__ == "__main__":
    main()
