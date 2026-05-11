"""
Analyze entry-known proxies for V50 fast losses.

Fast-loss labels are used only to discover candidate realtime filters. Any
candidate filter column is validated against leakage rules.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_feed.market_data import load_csv_data
from src.strategy_lab.v50_fast_loss_proxies import (
    DEFAULT_FAST_LOSS_PROXY_ANALYSIS_PATH,
    DEFAULT_FAST_LOSS_PROXY_CANDIDATES_PATH,
    build_fast_loss_proxy_analysis,
    build_fast_loss_proxy_candidates,
    build_fast_loss_proxy_dataset,
    export_fast_loss_proxy_reports,
    validate_no_leakage_columns,
)
from src.strategy_lab.v50_loss_intelligence import load_loss_trade_report


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Print and export fast-loss proxy diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Fast Loss Proxies")
    print("=" * 72)
    print("Mode: research/backtest only")

    trades = load_loss_trade_report()
    if trades is None:
        print("No strategy-tagged trade report found.")
        print("Run first: python scripts/run_strategy_lab.py --full")
        return

    market_data = load_csv_data(RAW_DATA_PATH) if RAW_DATA_PATH.exists() else None
    proxy_data = build_fast_loss_proxy_dataset(trades, market_data=market_data)
    analysis = build_fast_loss_proxy_analysis(proxy_data)
    candidates = build_fast_loss_proxy_candidates(proxy_data)
    validate_no_leakage_columns(candidates["filter_column"].dropna().unique().tolist())

    analysis_path, candidates_path = export_fast_loss_proxy_reports(
        analysis,
        candidates,
        DEFAULT_FAST_LOSS_PROXY_ANALYSIS_PATH,
        DEFAULT_FAST_LOSS_PROXY_CANDIDATES_PATH,
    )

    print("")
    print("Proxy group analysis:")
    _print_table(analysis)
    print("")
    print("Realtime-safe proxy candidates:")
    _print_table(candidates.head(30))
    print("")
    print(f"Fast-loss proxy analysis exported: {analysis_path}")
    print(f"Fast-loss proxy candidates exported: {candidates_path}")
    print("No strategy was promoted automatically.")


def _print_table(table: pd.DataFrame) -> None:
    if table.empty:
        print("(no data)")
        return
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
