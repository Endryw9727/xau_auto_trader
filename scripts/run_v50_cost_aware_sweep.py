"""
Run cost-aware V50 proxy sweep.

The sweep uses static research cost profiles and entry-known filters only.
It does not execute live trades.
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
    DEFAULT_COST_AWARE_SWEEP_PATH,
    run_cost_aware_sweep,
    run_source_variant_backtests,
)


RAW_DATA_PATH = Path("data/raw/xauusd.csv")


def main() -> None:
    """Run cost-aware sweep and export CSV."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Cost-Aware Sweep")
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
    report = run_cost_aware_sweep(
        source_results=source_results,
        market_data=df,
        value_per_point=backtest_config.value_per_point,
        output_path=DEFAULT_COST_AWARE_SWEEP_PATH,
        show_progress=True,
    )

    print("")
    print("Top cost_medium rows:")
    medium = report[report["cost_profile"] == "cost_medium"].copy()
    print(
        medium.sort_values(
            ["anti_overfit_pass", "net_profit_factor", "profit_drawdown_ratio_net", "net_profit"],
            ascending=[False, False, False, False],
        )
        .head(20)[
            [
                "source_variant",
                "variant_name",
                "total_trades",
                "average_trades_per_day",
                "net_profit_factor",
                "net_profit",
                "max_drawdown",
                "profit_drawdown_ratio_net",
                "anti_overfit_pass",
            ]
        ]
        .to_string(index=False)
    )
    print("")
    print(f"Cost-aware sweep exported: {DEFAULT_COST_AWARE_SWEEP_PATH}")
    print("No candidate was promoted automatically.")


if __name__ == "__main__":
    main()
