"""
Analyze the V50 proxy balanced candidate validation reports.

The script reads backtest, stress-test, and Monte Carlo reports. It only prints
research diagnostics and never promotes a strategy automatically.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy_lab.strategy_v50_candidates import (
    FINAL_BALANCED_STRATEGY_NAME,
    FINAL_GROWTH_STRATEGY_NAME,
    FINAL_LOW_RISK_STRATEGY_NAME,
)
from src.strategy_lab.strategy_v50_proxy_candidate import STRATEGY_NAME as PROXY_CANDIDATE_NAME
from src.strategy_lab.v50_monte_carlo import DEFAULT_V50_MONTE_CARLO_PATH
from src.strategy_lab.v50_stress_test import DEFAULT_V50_STRESS_TEST_PATH


STRATEGY_COMPARISON_PATH = Path("reports/strategy_lab/strategy_comparison.csv")
SELECTION_STRATEGIES = (
    FINAL_LOW_RISK_STRATEGY_NAME,
    FINAL_BALANCED_STRATEGY_NAME,
    FINAL_GROWTH_STRATEGY_NAME,
    PROXY_CANDIDATE_NAME,
)
COMPARISON_COLUMNS = [
    "strategy_name",
    "total_trades",
    "win_rate",
    "profit_factor",
    "net_profit",
    "max_drawdown",
    "expectancy",
    "profit_drawdown_ratio",
    "max_consecutive_losses",
    "average_trades_per_day",
]


def main() -> None:
    """Print V50 proxy candidate validation diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Proxy Candidate Selection")
    print("=" * 72)

    comparison = _load_required_csv(STRATEGY_COMPARISON_PATH)
    if comparison is None:
        print("Run first: python scripts/run_strategy_lab.py --full")
        return

    stress = _load_optional_csv(DEFAULT_V50_STRESS_TEST_PATH)
    monte_carlo = _load_optional_csv(DEFAULT_V50_MONTE_CARLO_PATH)
    comparison = prepare_strategy_comparison(comparison)

    print("")
    print("Base vs proxy_balanced_candidate:")
    _print_table(comparison[comparison["strategy_name"].isin([FINAL_BALANCED_STRATEGY_NAME, PROXY_CANDIDATE_NAME])])

    print("")
    print("Low risk / balanced / growth / proxy:")
    _print_table(comparison[comparison["strategy_name"].isin(SELECTION_STRATEGIES)])

    balanced = _strategy_row(comparison, FINAL_BALANCED_STRATEGY_NAME)
    proxy = _strategy_row(comparison, PROXY_CANDIDATE_NAME)

    print("")
    print("Validation checks:")
    print(f"Proxy beats balanced on PF: {proxy_beats_balanced_profit_factor(proxy, balanced)}")
    print(f"Proxy beats balanced on DD: {proxy_beats_balanced_drawdown(proxy, balanced)}")
    print(f"Proxy beats balanced on net profit: {proxy_beats_balanced_net_profit(proxy, balanced)}")
    print(f"Proxy stays above PF 1.20 under medium stress: {proxy_medium_stress_pf_ok(stress)}")
    print(f"Proxy Monte Carlo median DD is >20% lower than balanced: {proxy_monte_carlo_dd_20pct_better(monte_carlo)}")

    print("")
    print("Paper trading recommendation:")
    print(build_paper_trading_recommendation(comparison, stress, monte_carlo))
    print("")
    print("No candidate was promoted automatically.")


def prepare_strategy_comparison(comparison: pd.DataFrame) -> pd.DataFrame:
    """Normalize Strategy Lab comparison rows used by this report."""
    missing = set(COMPARISON_COLUMNS).difference(comparison.columns)
    if missing:
        raise ValueError("strategy comparison missing columns: " + ", ".join(sorted(missing)))

    result = comparison[comparison["strategy_name"].isin(SELECTION_STRATEGIES)].copy()
    for column in COMPARISON_COLUMNS:
        if column == "strategy_name":
            continue
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0.0)
    return result[COMPARISON_COLUMNS].sort_values("strategy_name").reset_index(drop=True)


def proxy_beats_balanced_profit_factor(proxy: pd.Series, balanced: pd.Series) -> bool:
    return bool(float(proxy["profit_factor"]) > float(balanced["profit_factor"]))


def proxy_beats_balanced_drawdown(proxy: pd.Series, balanced: pd.Series) -> bool:
    return bool(float(proxy["max_drawdown"]) < float(balanced["max_drawdown"]))


def proxy_beats_balanced_net_profit(proxy: pd.Series, balanced: pd.Series) -> bool:
    return bool(float(proxy["net_profit"]) > float(balanced["net_profit"]))


def proxy_medium_stress_pf_ok(stress: pd.DataFrame | None, min_profit_factor: float = 1.20) -> bool:
    if stress is None or stress.empty:
        return False
    row = stress[
        (stress["strategy_name"] == PROXY_CANDIDATE_NAME)
        & (stress["scenario"] == "spread_slippage_medium")
    ]
    if row.empty:
        return False
    return bool(float(row.iloc[0]["profit_factor"]) >= min_profit_factor)


def proxy_monte_carlo_dd_20pct_better(monte_carlo: pd.DataFrame | None) -> bool:
    if monte_carlo is None or monte_carlo.empty:
        return False
    balanced = monte_carlo[monte_carlo["strategy_name"] == FINAL_BALANCED_STRATEGY_NAME]
    proxy = monte_carlo[monte_carlo["strategy_name"] == PROXY_CANDIDATE_NAME]
    if balanced.empty or proxy.empty:
        return False
    balanced_dd = float(balanced.iloc[0]["median_max_drawdown"])
    proxy_dd = float(proxy.iloc[0]["median_max_drawdown"])
    return bool(proxy_dd <= balanced_dd * 0.80)


def build_paper_trading_recommendation(
    comparison: pd.DataFrame,
    stress: pd.DataFrame | None,
    monte_carlo: pd.DataFrame | None,
) -> str:
    """Return a conservative research recommendation without promotion."""
    balanced = _strategy_row(comparison, FINAL_BALANCED_STRATEGY_NAME)
    proxy = _strategy_row(comparison, PROXY_CANDIDATE_NAME)
    checks = [
        proxy_beats_balanced_profit_factor(proxy, balanced),
        proxy_beats_balanced_drawdown(proxy, balanced),
        proxy_beats_balanced_net_profit(proxy, balanced),
        proxy_medium_stress_pf_ok(stress),
    ]
    mc_dd_ok = proxy_monte_carlo_dd_20pct_better(monte_carlo)

    if all(checks) and mc_dd_ok:
        return (
            f"{PROXY_CANDIDATE_NAME} is the strongest research candidate for a controlled paper-trading validation. "
            "Keep it separate from live trading until out-of-sample paper evidence confirms the edge."
        )
    if checks[0] and checks[1] and checks[2]:
        return (
            f"{PROXY_CANDIDATE_NAME} improves full-history PF/DD/net versus balanced, "
            "but stress or Monte Carlo checks still need caution before paper validation."
        )
    return (
        f"{FINAL_BALANCED_STRATEGY_NAME} remains the safer reference candidate until "
        f"{PROXY_CANDIDATE_NAME} clears the validation checks."
    )


def _strategy_row(comparison: pd.DataFrame, strategy_name: str) -> pd.Series:
    row = comparison[comparison["strategy_name"] == strategy_name]
    if row.empty:
        raise ValueError(f"Missing strategy row: {strategy_name}")
    return row.iloc[0]


def _print_table(table: pd.DataFrame) -> None:
    if table.empty:
        print("(no data)")
        return
    print(table.to_string(index=False))


def _load_required_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        print(f"Missing report: {path}")
        return None
    print(f"Loaded report: {path}")
    return pd.read_csv(path)


def _load_optional_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        print(f"Optional report not found: {path}")
        return None
    print(f"Loaded report: {path}")
    return pd.read_csv(path)


if __name__ == "__main__":
    main()
