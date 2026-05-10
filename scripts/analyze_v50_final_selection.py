"""
Analyze final V50 candidates using comparison, stress, and Monte Carlo reports.

The output is advisory for research/paper trading only. It does not promote or
activate any strategy automatically.
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy_lab.strategy_v50_candidates import (
    FINAL_BALANCED_STRATEGY_NAME,
    FINAL_CANDIDATE_STRATEGY_NAMES,
    FINAL_GROWTH_STRATEGY_NAME,
    FINAL_LOW_RISK_STRATEGY_NAME,
)
from src.strategy_lab.v50_monte_carlo import DEFAULT_V50_MONTE_CARLO_PATH
from src.strategy_lab.v50_stress_test import DEFAULT_V50_STRESS_TEST_PATH


STRATEGY_COMPARISON_PATH = Path("reports/strategy_lab/strategy_comparison.csv")
FINAL_COMPARISON_COLUMNS = [
    "strategy_name",
    "total_trades",
    "win_rate",
    "profit_factor",
    "net_profit",
    "max_drawdown",
    "expectancy",
]
STRESS_SUMMARY_COLUMNS = [
    "strategy_name",
    "scenario_count",
    "worst_net_profit",
    "worst_profit_factor",
    "worst_max_drawdown",
    "worst_profit_drawdown_ratio",
    "worst_max_consecutive_losses",
]
MONTE_CARLO_COLUMNS = [
    "strategy_name",
    "iterations",
    "total_trades",
    "median_final_profit",
    "median_max_drawdown",
    "worst_5pct_drawdown",
    "probability_of_loss",
    "probability_drawdown_over_20_percent",
]


def main() -> None:
    """Print the final V50 selection report."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Final Selection")
    print("=" * 72)

    comparison = _load_optional_csv(STRATEGY_COMPARISON_PATH)
    stress = _load_optional_csv(DEFAULT_V50_STRESS_TEST_PATH)
    monte_carlo = _load_optional_csv(DEFAULT_V50_MONTE_CARLO_PATH)

    print("")
    print("Final candidate comparison:")
    comparison_table = final_candidate_comparison(comparison)
    _print_table(comparison_table, FINAL_COMPARISON_COLUMNS)

    print("")
    print("Stress-test summary:")
    stress_summary = summarize_stress_report(stress)
    _print_table(stress_summary, STRESS_SUMMARY_COLUMNS)

    print("")
    print("Monte Carlo summary:")
    monte_table = final_monte_carlo_report(monte_carlo)
    _print_table(monte_table, MONTE_CARLO_COLUMNS)

    print("")
    print("Recommended research use:")
    print(f"Paper trading: {FINAL_BALANCED_STRATEGY_NAME}")
    print(f"Low risk: {FINAL_LOW_RISK_STRATEGY_NAME}")
    print(f"Balanced: {FINAL_BALANCED_STRATEGY_NAME}")
    print(f"Aggressive: {FINAL_GROWTH_STRATEGY_NAME}")

    print("")
    print("No candidate was promoted automatically.")


def final_candidate_comparison(comparison: pd.DataFrame | None) -> pd.DataFrame:
    """Return Strategy Lab comparison rows for final candidates."""
    if comparison is None or comparison.empty or "strategy_name" not in comparison.columns:
        return pd.DataFrame(columns=FINAL_COMPARISON_COLUMNS)

    filtered = comparison[comparison["strategy_name"].isin(FINAL_CANDIDATE_STRATEGY_NAMES)].copy()
    return _ordered_by_final_names(filtered, FINAL_COMPARISON_COLUMNS)


def summarize_stress_report(stress: pd.DataFrame | None) -> pd.DataFrame:
    """Summarize worst stress-test values for each final candidate."""
    if stress is None or stress.empty or "strategy_name" not in stress.columns:
        return pd.DataFrame(columns=STRESS_SUMMARY_COLUMNS)

    rows = []
    filtered = stress[stress["strategy_name"].isin(FINAL_CANDIDATE_STRATEGY_NAMES)].copy()
    for column in [
        "net_profit",
        "profit_factor",
        "max_drawdown",
        "profit_drawdown_ratio",
        "max_consecutive_losses",
    ]:
        filtered[column] = pd.to_numeric(filtered[column], errors="coerce").replace([np.inf, -np.inf], np.nan)

    for strategy_name, group in filtered.groupby("strategy_name", sort=False):
        rows.append(
            {
                "strategy_name": strategy_name,
                "scenario_count": int(len(group)),
                "worst_net_profit": float(group["net_profit"].min()),
                "worst_profit_factor": float(group["profit_factor"].min()),
                "worst_max_drawdown": float(group["max_drawdown"].max()),
                "worst_profit_drawdown_ratio": float(group["profit_drawdown_ratio"].min()),
                "worst_max_consecutive_losses": int(group["max_consecutive_losses"].max()),
            }
        )

    return _ordered_by_final_names(pd.DataFrame(rows), STRESS_SUMMARY_COLUMNS)


def final_monte_carlo_report(monte_carlo: pd.DataFrame | None) -> pd.DataFrame:
    """Return Monte Carlo rows for final candidates."""
    if monte_carlo is None or monte_carlo.empty or "strategy_name" not in monte_carlo.columns:
        return pd.DataFrame(columns=MONTE_CARLO_COLUMNS)

    filtered = monte_carlo[monte_carlo["strategy_name"].isin(FINAL_CANDIDATE_STRATEGY_NAMES)].copy()
    return _ordered_by_final_names(filtered, MONTE_CARLO_COLUMNS)


def _ordered_by_final_names(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=columns)

    order = {strategy_name: index for index, strategy_name in enumerate(FINAL_CANDIDATE_STRATEGY_NAMES)}
    result = df.copy()
    result["_order"] = result["strategy_name"].map(order)
    result = result.sort_values("_order").drop(columns=["_order"])
    for column in columns:
        if column not in result.columns:
            result[column] = pd.NA
    return result[columns]


def _load_optional_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        print(f"Optional report not found: {path}")
        return None

    print(f"Loaded report: {path}")
    return pd.read_csv(path)


def _print_table(table: pd.DataFrame, columns: list[str]) -> None:
    if table.empty:
        print("(no data)")
        return

    print(table[columns].to_string(index=False))


if __name__ == "__main__":
    main()
