"""
Analyze daily coverage sweep results for final V50 balanced variants.

The report is advisory for research only. It does not promote any variant.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy_lab.v50_daily_coverage_sweep import DEFAULT_DAILY_COVERAGE_SWEEP_PATH


DISPLAY_COLUMNS = [
    "variant_name",
    "total_trades",
    "average_trades_per_day",
    "active_day_ratio",
    "profit_factor",
    "net_profit",
    "max_drawdown",
    "profit_drawdown_ratio",
    "max_consecutive_losses",
    "anti_overfit_pass",
]


def main() -> None:
    """Print daily coverage selection diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Daily Coverage Selection")
    print("=" * 72)

    sweep = _load_required_csv(DEFAULT_DAILY_COVERAGE_SWEEP_PATH)
    if sweep is None:
        print("Run first: python scripts/run_v50_daily_coverage_sweep.py")
        return

    ranking = prepare_daily_selection_ranking(sweep)
    base = _base_row(ranking)

    print("")
    print("Comparison against v50_final_balanced_strategy baseline:")
    print(base[DISPLAY_COLUMNS].to_frame().T.to_string(index=False))

    print("")
    print("Best pure quality:")
    _print_pick(select_best_pure_quality(ranking))

    print("")
    print("Best daily coverage:")
    _print_pick(select_best_daily_coverage(ranking))

    print("")
    print("Best balanced quality/coverage:")
    _print_pick(select_best_balanced_quality_coverage(ranking))

    print("")
    print("Best low drawdown:")
    _print_pick(select_best_low_drawdown(ranking))

    print("")
    print("Threshold checks:")
    print(f"PF >= 1.25 and average >= 1 trade/day: {_exists_pf_and_daily_average(ranking, 1.25, 1.0)}")
    print(f"Lower DD and average >= 0.8 trade/day: {_exists_lower_dd_with_daily_average(ranking, base, 0.8)}")

    print("")
    print("No variant was promoted automatically.")


def prepare_daily_selection_ranking(sweep: pd.DataFrame) -> pd.DataFrame:
    """Normalize and sort a daily coverage sweep report."""
    required = {
        "variant_name",
        "average_trades_per_day",
        "active_day_ratio",
        "profit_factor",
        "net_profit",
        "max_drawdown",
        "profit_drawdown_ratio",
        "max_consecutive_losses",
        "anti_overfit_pass",
    }
    missing = required.difference(sweep.columns)
    if missing:
        raise ValueError("daily coverage sweep missing columns: " + ", ".join(sorted(missing)))

    result = sweep.copy()
    for column in [
        "average_trades_per_day",
        "active_day_ratio",
        "profit_factor",
        "net_profit",
        "max_drawdown",
        "profit_drawdown_ratio",
        "max_consecutive_losses",
    ]:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0.0)
    result["anti_overfit_pass"] = result["anti_overfit_pass"].astype(bool)
    return result


def select_best_pure_quality(ranking: pd.DataFrame) -> pd.Series:
    """Pick the strongest PF variant with basic trade coverage."""
    eligible = ranking[ranking["total_trades"] >= 700].copy()
    if eligible.empty:
        eligible = ranking
    return eligible.sort_values(["profit_factor", "profit_drawdown_ratio"], ascending=[False, False]).iloc[0]


def select_best_daily_coverage(ranking: pd.DataFrame) -> pd.Series:
    """Pick the broadest daily coverage variant while keeping PF positive."""
    eligible = ranking[ranking["profit_factor"] >= 1.0].copy()
    if eligible.empty:
        eligible = ranking
    return eligible.sort_values(["average_trades_per_day", "active_day_ratio", "profit_factor"], ascending=False).iloc[0]


def select_best_balanced_quality_coverage(ranking: pd.DataFrame) -> pd.Series:
    """Pick the best quality/coverage balance."""
    eligible = ranking[ranking["anti_overfit_pass"]].copy()
    if eligible.empty:
        eligible = ranking
    return eligible.sort_values(
        ["profit_drawdown_ratio", "profit_factor", "average_trades_per_day"],
        ascending=False,
    ).iloc[0]


def select_best_low_drawdown(ranking: pd.DataFrame) -> pd.Series:
    """Pick the positive variant with lowest drawdown."""
    eligible = ranking[(ranking["net_profit"] > 0) & (ranking["max_drawdown"] > 0)].copy()
    if eligible.empty:
        eligible = ranking
    return eligible.sort_values(["max_drawdown", "profit_factor"], ascending=[True, False]).iloc[0]


def _exists_pf_and_daily_average(ranking: pd.DataFrame, min_pf: float, min_average: float) -> bool:
    return bool(
        ((ranking["profit_factor"] >= min_pf) & (ranking["average_trades_per_day"] >= min_average)).any()
    )


def _exists_lower_dd_with_daily_average(ranking: pd.DataFrame, base: pd.Series, min_average: float) -> bool:
    return bool(
        (
            (ranking["variant_name"] != base["variant_name"])
            & (ranking["max_drawdown"] < float(base["max_drawdown"]))
            & (ranking["average_trades_per_day"] >= min_average)
        ).any()
    )


def _base_row(ranking: pd.DataFrame) -> pd.Series:
    base = ranking[ranking["variant_name"] == "daily_base"]
    if base.empty:
        return ranking.iloc[0]
    return base.iloc[0]


def _print_pick(row: pd.Series) -> None:
    print(row[DISPLAY_COLUMNS].to_frame().T.to_string(index=False))


def _load_required_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        print(f"Missing report: {path}")
        return None
    print(f"Loaded report: {path}")
    return pd.read_csv(path)


if __name__ == "__main__":
    main()
