"""
Run Axi Pro paper/equity simulation for V50 research candidates.

This script uses local backtests only. It does not connect to a broker or place
live orders.
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
from src.strategy_lab.v50_axi_equity import (
    DEFAULT_AXI_EQUITY_CURVE_PATH,
    DEFAULT_AXI_EQUITY_SIMULATION_PATH,
    DEFAULT_AXI_MONTHLY_EQUITY_PATH,
    run_axi_equity_simulation,
)
from src.strategy_lab.v50_cost_aware import AxiSizingConfig, run_axi_source_backtests


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Run Axi paper/equity simulation and export reports."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Axi Equity Simulation")
    print("=" * 72)

    settings = load_settings()
    print(f"Live mode: {settings.trading.live_mode}")
    print("Mode: research/paper simulation only")

    if not RAW_DATA_PATH.exists():
        print(f"CSV file not found: {RAW_DATA_PATH}")
        return

    df = load_csv_data(RAW_DATA_PATH)
    strategy_config = build_strategy_config(settings)
    backtest_config = replace(build_backtest_config(settings), allowed_sessions=None)
    source_results = run_axi_source_backtests(
        df=df,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        show_progress=True,
    )
    summary, _curve, _monthly = run_axi_equity_simulation(
        source_results=source_results,
        market_data=df,
        sizing_config=AxiSizingConfig(),
        output_summary_path=DEFAULT_AXI_EQUITY_SIMULATION_PATH,
        output_curve_path=DEFAULT_AXI_EQUITY_CURVE_PATH,
        output_monthly_path=DEFAULT_AXI_MONTHLY_EQUITY_PATH,
    )

    print("")
    print("Axi equity summary:")
    print(
        summary.sort_values(
            ["scenario", "profit_factor_net", "net_profit_eur"],
            ascending=[True, False, False],
        )[
            [
                "strategy_name",
                "scenario",
                "ending_equity",
                "net_profit_eur",
                "max_drawdown_percent",
                "total_trades",
                "trades_per_day",
                "profit_factor_net",
                "max_consecutive_losses",
                "lot_max",
            ]
        ].to_string(index=False)
    )
    print("")
    print(f"Summary exported: {DEFAULT_AXI_EQUITY_SIMULATION_PATH}")
    print(f"Equity curve exported: {DEFAULT_AXI_EQUITY_CURVE_PATH}")
    print(f"Monthly equity exported: {DEFAULT_AXI_MONTHLY_EQUITY_PATH}")
    print("No candidate was promoted automatically.")


if __name__ == "__main__":
    main()
