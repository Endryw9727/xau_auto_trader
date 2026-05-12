"""
Run V50 candidates with Axi Pro real-cost assumptions.

This is research-only backtesting. It does not connect to Axi or execute live
orders.
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
    AxiSizingConfig,
    DEFAULT_AXI_REAL_COST_BACKTEST_PATH,
    axi_real_cost_profiles,
    run_axi_real_cost_backtest,
    run_axi_source_backtests,
)


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Run Axi real-cost backtest report."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Axi Real-Cost Backtest")
    print("=" * 72)

    settings = load_settings()
    print(f"Live mode: {settings.trading.live_mode}")
    print("Mode: research/backtest only")
    print("Broker cost profile: Axi Pro static research model")

    if not RAW_DATA_PATH.exists():
        print(f"CSV file not found: {RAW_DATA_PATH}")
        return

    df = load_csv_data(RAW_DATA_PATH)
    strategy_config = build_strategy_config(settings)
    backtest_config = replace(build_backtest_config(settings), allowed_sessions=None)
    sizing_config = AxiSizingConfig()

    source_results = run_axi_source_backtests(
        df=df,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        show_progress=True,
    )
    report = run_axi_real_cost_backtest(
        source_results=source_results,
        market_data=df,
        profiles=axi_real_cost_profiles(),
        sizing_config=sizing_config,
        value_per_point=backtest_config.value_per_point,
        output_path=DEFAULT_AXI_REAL_COST_BACKTEST_PATH,
    )

    print("")
    print("Axi realistic:")
    realistic = report[report["cost_profile"] == "axi_pro_realistic"].copy()
    print(
        realistic.sort_values(["net_profit_factor", "profit_drawdown_ratio_after_costs"], ascending=False)[
            [
                "strategy_name",
                "total_trades",
                "average_trades_per_day",
                "net_profit_factor",
                "net_profit_after_costs",
                "average_cost_per_trade",
                "average_trade_after_costs",
                "max_drawdown_after_costs",
            ]
        ].to_string(index=False)
    )
    print("")
    print("Axi conservative:")
    conservative = report[report["cost_profile"] == "axi_pro_conservative"].copy()
    print(
        conservative.sort_values(["net_profit_factor", "profit_drawdown_ratio_after_costs"], ascending=False)[
            [
                "strategy_name",
                "total_trades",
                "average_trades_per_day",
                "net_profit_factor",
                "net_profit_after_costs",
                "average_cost_per_trade",
                "average_trade_after_costs",
                "max_drawdown_after_costs",
            ]
        ].to_string(index=False)
    )
    print("")
    print(f"Axi real-cost backtest exported: {DEFAULT_AXI_REAL_COST_BACKTEST_PATH}")
    print("No candidate was promoted automatically.")


if __name__ == "__main__":
    main()
