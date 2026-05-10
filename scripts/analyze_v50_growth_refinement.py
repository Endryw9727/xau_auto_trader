"""
Analyze V50 growth-refinement sweep reports.

The script ranks variants from local CSV reports and does not promote any
variant automatically.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy_lab.v50_growth_refinement_sweep import (
    DEFAULT_GROWTH_REFINEMENT_SWEEP_PATH,
    DEFAULT_GROWTH_REFINEMENT_WALK_FORWARD_MONTH_PATH,
    DEFAULT_GROWTH_REFINEMENT_WALK_FORWARD_QUARTER_PATH,
)


RANKING_COLUMNS = [
    "variant_name",
    "stability_score",
    "profit_drawdown_ratio",
    "profit_factor",
    "net_profit",
    "max_drawdown",
    "total_trades",
]


def main() -> None:
    """Print the growth-refinement ranking and category picks."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Growth Refinement Analysis")
    print("=" * 72)

    sweep = _load_required_csv(DEFAULT_GROWTH_REFINEMENT_SWEEP_PATH)
    if sweep is None:
        print("Run first: python scripts/run_v50_growth_refinement_sweep.py")
        return

    quarter = _load_optional_csv(DEFAULT_GROWTH_REFINEMENT_WALK_FORWARD_QUARTER_PATH)
    month = _load_optional_csv(DEFAULT_GROWTH_REFINEMENT_WALK_FORWARD_MONTH_PATH)
    ranking = build_growth_refinement_ranking(sweep, quarter=quarter, month=month)

    print("")
    print("Ranking by stability, profit/drawdown, profit factor, net profit:")
    print(ranking[RANKING_COLUMNS].to_string(index=False))

    print("")
    print("Category picks:")
    _print_pick("Best low risk", select_best_low_risk(ranking))
    _print_pick("Best balanced", select_best_balanced(ranking))
    _print_pick("Best growth", select_best_growth(ranking))

    print("")
    print("No variant was promoted automatically.")


def build_growth_refinement_ranking(
    sweep: pd.DataFrame,
    quarter: pd.DataFrame | None = None,
    month: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Merge full-history and walk-forward reports into one sortable ranking."""
    required = {"variant_name", "profit_drawdown_ratio", "profit_factor", "net_profit", "max_drawdown", "total_trades"}
    missing = required.difference(sweep.columns)
    if missing:
        raise ValueError("sweep report is missing required columns: " + ", ".join(sorted(missing)))

    ranking = sweep.copy()
    stability = _stability_lookup(month)
    if not stability:
        stability = _stability_lookup(quarter)

    ranking["stability_score"] = ranking["variant_name"].map(stability).fillna(0.0)
    numeric_columns = [
        "stability_score",
        "profit_drawdown_ratio",
        "profit_factor",
        "net_profit",
        "max_drawdown",
        "total_trades",
    ]
    for column in numeric_columns:
        ranking[column] = pd.to_numeric(ranking[column], errors="coerce").fillna(0.0)

    return ranking.sort_values(
        ["stability_score", "profit_drawdown_ratio", "profit_factor", "net_profit"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)


def select_best_low_risk(ranking: pd.DataFrame) -> pd.Series:
    """Select the positive variant with the lowest drawdown."""
    eligible = ranking[(ranking["net_profit"] > 0) & (ranking["max_drawdown"] > 0)].copy()
    if eligible.empty:
        return ranking.iloc[0]

    return eligible.sort_values(
        ["max_drawdown", "stability_score", "profit_drawdown_ratio"],
        ascending=[True, False, False],
    ).iloc[0]


def select_best_balanced(ranking: pd.DataFrame) -> pd.Series:
    """Select the variant with the strongest stability-adjusted balance."""
    return ranking.sort_values(
        ["stability_score", "profit_drawdown_ratio", "profit_factor", "net_profit"],
        ascending=[False, False, False, False],
    ).iloc[0]


def select_best_growth(ranking: pd.DataFrame) -> pd.Series:
    """Select the positive variant with the highest full-history net profit."""
    eligible = ranking[ranking["net_profit"] > 0].copy()
    if eligible.empty:
        return ranking.iloc[0]

    return eligible.sort_values(
        ["net_profit", "stability_score", "profit_drawdown_ratio"],
        ascending=[False, False, False],
    ).iloc[0]


def _stability_lookup(report: pd.DataFrame | None) -> dict[str, float]:
    if report is None or report.empty:
        return {}
    if not {"variant_name", "stability_score"}.issubset(report.columns):
        return {}

    prepared = report.copy()
    prepared["stability_score"] = pd.to_numeric(prepared["stability_score"], errors="coerce").fillna(0.0)
    return dict(zip(prepared["variant_name"], prepared["stability_score"], strict=False))


def _print_pick(title: str, row: pd.Series) -> None:
    print(
        f"{title}: {row['variant_name']} | "
        f"stability={float(row['stability_score']):.3f} | "
        f"PF={float(row['profit_factor']):.3f} | "
        f"net={float(row['net_profit']):.2f} | "
        f"DD={float(row['max_drawdown']):.2f} | "
        f"P/DD={float(row['profit_drawdown_ratio']):.3f}"
    )


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
