"""
Audit V50 cost model assumptions.

This script is research-only. It does not execute live trades or call brokers.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_feed.market_data import load_csv_data
from src.main import build_backtest_config, build_strategy_config
from src.settings import load_settings
from src.strategy_lab.v50_cost_aware import (
    DEFAULT_COST_MODEL_AUDIT_PATH,
    build_cost_model_audit,
    export_cost_model_audit,
    run_source_variant_backtests,
)


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Run the cost-model audit and export a CSV."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Cost Model Audit")
    print("=" * 72)

    settings = load_settings()
    print(f"Live mode: {settings.trading.live_mode}")
    print("Mode: research/backtest only")

    if not RAW_DATA_PATH.exists():
        print(f"CSV file not found: {RAW_DATA_PATH}")
        return

    df = load_csv_data(RAW_DATA_PATH)
    strategy_config = build_strategy_config(settings)
    backtest_config = replace(build_backtest_config(settings), allowed_sessions=None)
    source_results = run_source_variant_backtests(
        df=df,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        show_progress=True,
    )
    audit = build_cost_model_audit(
        source_results,
        value_per_point=backtest_config.value_per_point,
    )
    export_cost_model_audit(audit, DEFAULT_COST_MODEL_AUDIT_PATH)

    print("")
    print("Audit summary:")
    summary = audit[audit["group_type"] == "variant"].copy()
    print(
        summary[
            [
                "source_variant",
                "cost_profile",
                "total_trades",
                "gross_net_profit",
                "net_profit",
                "total_cost",
                "average_cost_per_trade",
                "round_turn_cost_points",
            ]
        ].to_string(index=False)
    )
    print("")
    print("Backtester cost finding:")
    print("Slippage is applied on entry and exit; fixed commission is applied once per closed trade.")
    print("Native spread and partial exits are not currently modeled in the core backtester.")
    print(f"Cost model audit exported: {DEFAULT_COST_MODEL_AUDIT_PATH}")
    print("No candidate was promoted automatically.")


if __name__ == "__main__":
    main()
