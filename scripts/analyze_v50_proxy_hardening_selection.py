"""
Analyze V50 proxy hardening sweep results.

The script compares hardening variants without promoting any strategy.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy_lab.v50_proxy_hardening import (
    DEFAULT_PROXY_HARDENING_MONTE_CARLO_PATH,
    DEFAULT_PROXY_HARDENING_STRESS_PATH,
    DEFAULT_PROXY_HARDENING_SWEEP_PATH,
)


DISPLAY_COLUMNS = [
    "variant_name",
    "total_trades",
    "average_trades_per_day",
    "profit_factor",
    "net_profit",
    "max_drawdown",
    "profit_drawdown_ratio",
    "max_consecutive_losses",
    "anti_overfit_pass",
]


def main() -> None:
    """Print hardening selection diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Proxy Hardening Selection")
    print("=" * 72)

    sweep = _load_required_csv(DEFAULT_PROXY_HARDENING_SWEEP_PATH)
    stress = _load_required_csv(DEFAULT_PROXY_HARDENING_STRESS_PATH)
    monte_carlo = _load_required_csv(DEFAULT_PROXY_HARDENING_MONTE_CARLO_PATH)
    if sweep is None or stress is None or monte_carlo is None:
        print("Run first: python scripts/run_v50_proxy_hardening_sweep.py")
        return

    ranking = prepare_hardening_ranking(sweep)
    print("")
    print("Proxy base vs hardened variants:")
    _print_table(ranking[DISPLAY_COLUMNS])
    _print_pick("Best PF", select_best_profit_factor(ranking))
    _print_pick("Best DD", select_best_drawdown(ranking))
    _print_pick("Best Monte Carlo", select_best_monte_carlo(ranking, monte_carlo))
    _print_pick("Best medium stress", select_best_medium_stress(ranking, stress))
    _print_pick("Best quality/coverage compromise", select_best_quality_coverage(ranking))

    print("")
    print("Threshold checks:")
    print(f"PF full >= 1.23 and stress medium >= 1.20: {exists_pf_and_medium_stress(ranking, stress)}")
    print(f"DD <= 135 and Monte Carlo better than base: {exists_low_dd_and_mc_better(ranking, monte_carlo)}")
    print("")
    print("Paper trading recommendation:")
    print(build_hardening_recommendation(ranking, stress, monte_carlo))
    print("")
    print("No candidate was promoted automatically.")


def prepare_hardening_ranking(sweep: pd.DataFrame) -> pd.DataFrame:
    """Normalize hardening sweep rows for ranking."""
    result = sweep.copy()
    required = set(DISPLAY_COLUMNS + ["leakage_safe"])
    missing = required.difference(result.columns)
    if missing:
        raise ValueError("hardening sweep missing columns: " + ", ".join(sorted(missing)))
    numeric = [column for column in DISPLAY_COLUMNS if column != "variant_name" and column != "anti_overfit_pass"]
    for column in numeric:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0.0)
    result["anti_overfit_pass"] = result["anti_overfit_pass"].astype(bool)
    result["leakage_safe"] = result["leakage_safe"].astype(bool)
    return result


def select_best_profit_factor(ranking: pd.DataFrame) -> pd.Series:
    return _eligible_or_all(ranking).sort_values(["profit_factor", "average_trades_per_day"], ascending=False).iloc[0]


def select_best_drawdown(ranking: pd.DataFrame) -> pd.Series:
    eligible = _eligible_or_all(ranking)
    return eligible[eligible["max_drawdown"] > 0].sort_values(["max_drawdown", "profit_factor"], ascending=[True, False]).iloc[0]


def select_best_quality_coverage(ranking: pd.DataFrame) -> pd.Series:
    eligible = ranking[ranking["anti_overfit_pass"] & ranking["leakage_safe"]]
    if eligible.empty:
        eligible = _eligible_or_all(ranking)
    return eligible.sort_values(
        ["profit_drawdown_ratio", "profit_factor", "average_trades_per_day"],
        ascending=False,
    ).iloc[0]


def select_best_medium_stress(ranking: pd.DataFrame, stress: pd.DataFrame) -> pd.Series:
    medium = _medium_stress(stress)
    merged = ranking.drop(columns=["stress_medium_profit_factor"], errors="ignore").merge(
        medium,
        on="variant_name",
        how="left",
    )
    merged["stress_medium_profit_factor"] = merged["stress_medium_profit_factor"].fillna(0.0)
    return merged.sort_values(["stress_medium_profit_factor", "profit_factor"], ascending=False).iloc[0]


def select_best_monte_carlo(ranking: pd.DataFrame, monte_carlo: pd.DataFrame) -> pd.Series:
    mc = monte_carlo.rename(columns={"strategy_name": "variant_name"})
    base = ranking.drop(
        columns=["probability_drawdown_over_20_percent", "median_max_drawdown"],
        errors="ignore",
    )
    merged = base.merge(
        mc[["variant_name", "probability_drawdown_over_20_percent", "median_max_drawdown"]],
        on="variant_name",
        how="left",
    )
    merged["probability_drawdown_over_20_percent"] = merged["probability_drawdown_over_20_percent"].fillna(100.0)
    merged["median_max_drawdown"] = merged["median_max_drawdown"].fillna(999999.0)
    return merged.sort_values(["probability_drawdown_over_20_percent", "median_max_drawdown"]).iloc[0]


def exists_pf_and_medium_stress(ranking: pd.DataFrame, stress: pd.DataFrame) -> bool:
    medium = _medium_stress(stress)
    merged = ranking.drop(columns=["stress_medium_profit_factor"], errors="ignore").merge(
        medium,
        on="variant_name",
        how="left",
    )
    return bool(((merged["profit_factor"] >= 1.23) & (merged["stress_medium_profit_factor"] >= 1.20)).any())


def exists_low_dd_and_mc_better(ranking: pd.DataFrame, monte_carlo: pd.DataFrame) -> bool:
    mc = monte_carlo.rename(columns={"strategy_name": "variant_name"})
    base = mc[mc["variant_name"] == "proxy_hardened_base"]
    if base.empty:
        return False
    base_probability = float(base.iloc[0]["probability_drawdown_over_20_percent"])
    merged = ranking.drop(columns=["probability_drawdown_over_20_percent"], errors="ignore").merge(
        mc[["variant_name", "probability_drawdown_over_20_percent"]],
        on="variant_name",
        how="left",
    )
    return bool(
        (
            (merged["max_drawdown"] <= 135.0)
            & (merged["probability_drawdown_over_20_percent"] < base_probability)
            & merged["leakage_safe"]
        ).any()
    )


def build_hardening_recommendation(
    ranking: pd.DataFrame,
    stress: pd.DataFrame,
    monte_carlo: pd.DataFrame,
) -> str:
    """Build a cautious recommendation without promotion."""
    passing = ranking[ranking["anti_overfit_pass"] & ranking["leakage_safe"]]
    if not passing.empty:
        row = select_best_quality_coverage(passing)
        return (
            f"{row['variant_name']} is the strongest hardening candidate for a controlled paper-trading study. "
            "Keep it research-only until paper evidence confirms robustness."
        )
    return (
        "No hardening variant clears all robustness gates. Keep v50_proxy_balanced_candidate as the reference "
        "research candidate and continue diagnosis before paper deployment."
    )


def _eligible_or_all(ranking: pd.DataFrame) -> pd.DataFrame:
    eligible = ranking[(ranking["total_trades"] >= 850) & (ranking["average_trades_per_day"] >= 0.75) & ranking["leakage_safe"]]
    return eligible if not eligible.empty else ranking[ranking["leakage_safe"]]


def _medium_stress(stress: pd.DataFrame) -> pd.DataFrame:
    return stress[stress["scenario"] == "spread_slippage_medium"][
        ["variant_name", "profit_factor"]
    ].rename(columns={"profit_factor": "stress_medium_profit_factor"})


def _print_pick(title: str, row: pd.Series) -> None:
    print("")
    print(title + ":")
    print(row[DISPLAY_COLUMNS].to_frame().T.to_string(index=False))


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


if __name__ == "__main__":
    main()
