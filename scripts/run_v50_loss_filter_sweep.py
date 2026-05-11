"""
Run counterfactual loss-filter sweep for v50_final_balanced_strategy.

The sweep operates on simulated backtest trades. It does not promote variants.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_feed.market_data import load_csv_data
from src.strategy_lab.v50_loss_filter_sweep import (
    DEFAULT_LOSS_FILTER_SWEEP_PATH,
    run_v50_loss_filter_sweep,
    sort_loss_filter_sweep,
)
from src.strategy_lab.v50_loss_intelligence import load_loss_trade_report


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Run the V50 loss-filter sweep from local reports."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Loss Filter Sweep")
    print("=" * 72)
    print("Mode: research/backtest only")

    trades = load_loss_trade_report()
    if trades is None:
        print("No strategy-tagged trade report found.")
        print("Run first: python scripts/run_strategy_lab.py --full")
        return

    market_data = load_csv_data(RAW_DATA_PATH) if RAW_DATA_PATH.exists() else None
    report = run_v50_loss_filter_sweep(
        trades=trades,
        market_data=market_data,
        output_path=DEFAULT_LOSS_FILTER_SWEEP_PATH,
    )

    print("")
    print("Loss filter sweep:")
    print(sort_loss_filter_sweep(report).to_string(index=False))
    print("")
    print(f"Loss filter sweep exported: {DEFAULT_LOSS_FILTER_SWEEP_PATH}")
    print("No variant was promoted automatically.")


if __name__ == "__main__":
    main()
