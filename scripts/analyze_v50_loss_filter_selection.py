"""
Analyze V50 loss-filter sweep results.

The output is advisory for research only. No variant is promoted.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy_lab.v50_loss_filter_sweep import DEFAULT_LOSS_FILTER_SWEEP_PATH


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
    """Print loss-filter selection diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Loss Filter Selection")
    print("=" * 72)

    sweep = _load_required_csv(DEFAULT_LOSS_FILTER_SWEEP_PATH)
    if sweep is None:
        print("Run first: python scripts/run_v50_loss_filter_sweep.py")
        return

    ranking = prepare_loss_filter_ranking(sweep)
    base = base_row(ranking)

    print("")
    print("Comparison against v50_final_balanced_strategy:")
    print(base[DISPLAY_COLUMNS].to_frame().T.to_string(index=False))

    _print_pick("Best profit factor", select_best_profit_factor(ranking))
    _print_pick("Best drawdown", select_best_drawdown(ranking))
    _print_pick("Best profit/drawdown", select_best_profit_drawdown(ranking))
    _print_pick("Best loss-streak reduction", select_best_loss_streak_reduction(ranking, base))
    _print_pick("Best quality/coverage compromise", select_best_quality_coverage(ranking))

    print("")
    print("Threshold checks:")
    print(f"PF >= 1.25 with >= 0.75 trade/day: {exists_pf_with_frequency(ranking, 1.25, 0.75)}")
    print(f"PF >= 1.20 with DD lower by 20%: {exists_pf_with_dd_reduction(ranking, base, 1.20, 0.20)}")

    print("")
    print("No variant was promoted automatically.")


def prepare_loss_filter_ranking(sweep: pd.DataFrame) -> pd.DataFrame:
    """Normalize loss-filter sweep data."""
    required = set(DISPLAY_COLUMNS)
    missing = required.difference(sweep.columns)
    if missing:
        raise ValueError("loss-filter sweep missing columns: " + ", ".join(sorted(missing)))

    result = sweep.copy()
    for column in [
        "total_trades",
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


def base_row(ranking: pd.DataFrame) -> pd.Series:
    base = ranking[ranking["variant_name"] == "loss_filter_base"]
    return base.iloc[0] if not base.empty else ranking.iloc[0]


def select_best_profit_factor(ranking: pd.DataFrame) -> pd.Series:
    eligible = _eligible_or_all(ranking)
    return eligible.sort_values(["profit_factor", "average_trades_per_day"], ascending=False).iloc[0]


def select_best_drawdown(ranking: pd.DataFrame) -> pd.Series:
    eligible = _eligible_or_all(ranking)
    return eligible[eligible["max_drawdown"] > 0].sort_values(["max_drawdown", "profit_factor"], ascending=[True, False]).iloc[0]


def select_best_profit_drawdown(ranking: pd.DataFrame) -> pd.Series:
    eligible = _eligible_or_all(ranking)
    return eligible.sort_values(["profit_drawdown_ratio", "profit_factor"], ascending=False).iloc[0]


def select_best_loss_streak_reduction(ranking: pd.DataFrame, base: pd.Series) -> pd.Series:
    result = ranking.copy()
    result["loss_streak_reduction"] = float(base["max_consecutive_losses"]) - result["max_consecutive_losses"]
    eligible = result[(result["total_trades"] >= 700) & (result["net_profit"] > 0)]
    if eligible.empty:
        eligible = result
    return eligible.sort_values(["loss_streak_reduction", "profit_factor"], ascending=False).iloc[0]


def select_best_quality_coverage(ranking: pd.DataFrame) -> pd.Series:
    eligible = _eligible_or_all(ranking)
    return eligible.sort_values(
        ["anti_overfit_pass", "profit_drawdown_ratio", "average_trades_per_day"],
        ascending=False,
    ).iloc[0]


def exists_pf_with_frequency(ranking: pd.DataFrame, min_pf: float, min_average: float) -> bool:
    return bool(
        ((ranking["profit_factor"] >= min_pf) & (ranking["average_trades_per_day"] >= min_average)).any()
    )


def exists_pf_with_dd_reduction(
    ranking: pd.DataFrame,
    base: pd.Series,
    min_pf: float,
    dd_reduction: float,
) -> bool:
    threshold = float(base["max_drawdown"]) * (1.0 - dd_reduction)
    return bool(((ranking["profit_factor"] >= min_pf) & (ranking["max_drawdown"] <= threshold)).any())


def _eligible_or_all(ranking: pd.DataFrame) -> pd.DataFrame:
    eligible = ranking[(ranking["total_trades"] >= 700) & (ranking["average_trades_per_day"] >= 0.75)].copy()
    return eligible if not eligible.empty else ranking


def _print_pick(title: str, row: pd.Series) -> None:
    print("")
    print(title + ":")
    print(row[DISPLAY_COLUMNS].to_frame().T.to_string(index=False))


def _load_required_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        print(f"Missing report: {path}")
        return None
    print(f"Loaded report: {path}")
    return pd.read_csv(path)


if __name__ == "__main__":
    main()
