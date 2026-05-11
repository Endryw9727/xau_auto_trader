"""
Run realtime-safe hardening sweep for v50_proxy_balanced_candidate.

This is research-only backtesting. It does not execute live trades.
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
from src.strategy_lab.v50_proxy_hardening import (
    DEFAULT_PROXY_HARDENING_MONTE_CARLO_PATH,
    DEFAULT_PROXY_HARDENING_STRESS_PATH,
    DEFAULT_PROXY_HARDENING_SWEEP_PATH,
    annotate_hardening_interest,
    run_proxy_hardening_monte_carlo,
    run_proxy_hardening_stress,
    run_proxy_hardening_sweep,
)


RAW_DATA_PATH = Path("data/raw/xauusd.csv")
BASE_PROXY_DD20_PROBABILITY = 32.4
MONTE_CARLO_ITERATIONS = 500


def main() -> None:
    """Run hardening sweep, stress tests and Monte Carlo."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Proxy Hardening Sweep")
    print("=" * 72)

    settings = load_settings()
    if not RAW_DATA_PATH.exists():
        print(f"CSV file not found: {RAW_DATA_PATH}")
        return

    print(f"Symbol: {settings.trading.symbol}")
    print(f"Base timeframe: {settings.trading.base_timeframe}")
    print(f"Live mode: {settings.trading.live_mode}")
    print("Mode: research/backtest only")
    print("")

    df = load_csv_data(RAW_DATA_PATH)
    strategy_config = build_strategy_config(settings)
    backtest_config = replace(build_backtest_config(settings), allowed_sessions=None)

    sweep, results = run_proxy_hardening_sweep(
        df=df,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        output_path=DEFAULT_PROXY_HARDENING_SWEEP_PATH,
        show_progress=True,
    )
    stress = run_proxy_hardening_stress(
        df=df,
        sweep_report=sweep,
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        output_path=DEFAULT_PROXY_HARDENING_STRESS_PATH,
        show_progress=True,
    )
    monte_carlo = run_proxy_hardening_monte_carlo(
        results=results,
        sweep_report=sweep,
        initial_balance=backtest_config.initial_balance,
        iterations=MONTE_CARLO_ITERATIONS,
        output_path=DEFAULT_PROXY_HARDENING_MONTE_CARLO_PATH,
    )
    sweep = annotate_hardening_interest(
        sweep,
        stress,
        monte_carlo,
        base_probability_dd20=BASE_PROXY_DD20_PROBABILITY,
    )
    sweep.to_csv(DEFAULT_PROXY_HARDENING_SWEEP_PATH, index=False)

    print("")
    print("Hardening sweep:")
    print(sweep.to_string(index=False))
    print("")
    print("Hardening stress:")
    print(stress.to_string(index=False))
    print("")
    print("Hardening Monte Carlo:")
    print(monte_carlo.to_string(index=False))
    print("")
    print(f"Hardening sweep exported: {DEFAULT_PROXY_HARDENING_SWEEP_PATH}")
    print(f"Hardening stress exported: {DEFAULT_PROXY_HARDENING_STRESS_PATH}")
    print(f"Hardening Monte Carlo exported: {DEFAULT_PROXY_HARDENING_MONTE_CARLO_PATH}")
    print("No candidate was promoted automatically.")


if __name__ == "__main__":
    main()
