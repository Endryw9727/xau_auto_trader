"""
Diagnostics helpers for Strategy Lab walk-forward reports.

The module only reads backtest report data and calculates robustness metrics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


DEFAULT_DIAGNOSTIC_STRATEGIES = (
    "v50_pine_technical_strategy",
    "v50_low_risk_london_strategy",
    "v50_balanced_no_asia_london_strategy",
    "v50_growth_long_all_short_london_strategy",
    "v50_final_low_risk_strategy",
    "v50_final_balanced_strategy",
    "v50_final_growth_strategy",
    "v50_pine_mtf_strategy",
    "mtf_relaxed_offasia_strategy",
    "mtf_feature_filtered_strategy",
)
STRATEGY_DIAGNOSTICS_REPORT_PATH = Path("reports/strategy_lab/strategy_diagnostics.csv")
REQUIRED_WALK_FORWARD_COLUMNS = {
    "strategy_name",
    "total_trades",
    "profit_factor",
    "net_profit",
    "max_drawdown",
}
DIAGNOSTIC_COLUMNS = [
    "strategy_name",
    "total_periods",
    "active_periods",
    "no_trade_periods",
    "positive_periods",
    "negative_periods",
    "total_trades",
    "avg_trades_per_active_period",
    "average_profit_factor",
    "median_profit_factor",
    "total_net_profit",
    "worst_period_net_profit",
    "worst_period_drawdown",
    "profit_drawdown_ratio",
    "active_coverage",
    "positive_active_ratio",
    "normalized_profit_drawdown_ratio",
    "coverage_penalty",
    "profit_factor_penalty",
    "drawdown_penalty",
    "stability_score",
    "full_total_trades",
    "full_profit_factor",
    "full_net_profit",
    "full_max_drawdown",
]


def build_strategy_diagnostics(
    walk_forward: pd.DataFrame,
    strategy_comparison: pd.DataFrame | None = None,
    strategy_names: Iterable[str] = DEFAULT_DIAGNOSTIC_STRATEGIES,
) -> pd.DataFrame:
    """Build a strategy robustness ranking from walk-forward period rows."""
    _validate_walk_forward_columns(walk_forward)

    selected_names = list(strategy_names)
    prepared = _prepare_walk_forward_rows(walk_forward, selected_names)
    full_history = _full_history_lookup(strategy_comparison)

    rows = [
        _diagnostic_row(strategy_name, group, full_history)
        for strategy_name, group in prepared.groupby("strategy_name", sort=True)
    ]
    diagnostics = pd.DataFrame(rows)

    if diagnostics.empty:
        return pd.DataFrame(columns=DIAGNOSTIC_COLUMNS)

    diagnostics = _add_score_components(diagnostics)
    diagnostics = diagnostics.sort_values(
        ["stability_score", "total_net_profit"],
        ascending=[False, False],
    ).reset_index(drop=True)

    return diagnostics[DIAGNOSTIC_COLUMNS]


def export_strategy_diagnostics(
    diagnostics: pd.DataFrame,
    output_path: str | Path = STRATEGY_DIAGNOSTICS_REPORT_PATH,
) -> Path:
    """Export diagnostics to CSV and return the written path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(output_path, index=False)
    return output_path


def _validate_walk_forward_columns(walk_forward: pd.DataFrame) -> None:
    missing = REQUIRED_WALK_FORWARD_COLUMNS.difference(walk_forward.columns)
    if missing:
        raise ValueError(
            "walk_forward is missing required columns: "
            + ", ".join(sorted(missing))
        )


def _prepare_walk_forward_rows(
    walk_forward: pd.DataFrame,
    strategy_names: list[str],
) -> pd.DataFrame:
    prepared = walk_forward[walk_forward["strategy_name"].isin(strategy_names)].copy()

    for column in ["total_trades", "profit_factor", "net_profit", "max_drawdown"]:
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce").fillna(0.0)

    return prepared


def _full_history_lookup(strategy_comparison: pd.DataFrame | None) -> dict[str, dict]:
    if strategy_comparison is None or strategy_comparison.empty:
        return {}

    required_columns = {"strategy_name", "total_trades", "profit_factor", "net_profit", "max_drawdown"}
    if not required_columns.issubset(strategy_comparison.columns):
        return {}

    comparison = strategy_comparison.copy()
    for column in ["total_trades", "profit_factor", "net_profit", "max_drawdown"]:
        comparison[column] = pd.to_numeric(comparison[column], errors="coerce").fillna(0.0)

    return comparison.set_index("strategy_name")[
        ["total_trades", "profit_factor", "net_profit", "max_drawdown"]
    ].to_dict(orient="index")


def _diagnostic_row(
    strategy_name: str,
    group: pd.DataFrame,
    full_history: dict[str, dict],
) -> dict:
    active = group[group["total_trades"] > 0]
    total_periods = int(len(group))
    active_periods = int(len(active))
    total_trades = int(group["total_trades"].sum())
    active_profit_factors = _finite_profit_factors(active["profit_factor"])
    worst_period_drawdown = float(group["max_drawdown"].max())
    total_net_profit = float(group["net_profit"].sum())
    full_row = full_history.get(strategy_name, {})

    return {
        "strategy_name": strategy_name,
        "total_periods": total_periods,
        "active_periods": active_periods,
        "no_trade_periods": total_periods - active_periods,
        "positive_periods": int((group["net_profit"] > 0).sum()),
        "negative_periods": int((group["net_profit"] < 0).sum()),
        "total_trades": total_trades,
        "avg_trades_per_active_period": _safe_div(total_trades, active_periods),
        "average_profit_factor": _mean_or_zero(active_profit_factors),
        "median_profit_factor": _median_or_zero(active_profit_factors),
        "total_net_profit": total_net_profit,
        "worst_period_net_profit": float(group["net_profit"].min()),
        "worst_period_drawdown": worst_period_drawdown,
        "profit_drawdown_ratio": _safe_div(total_net_profit, worst_period_drawdown),
        "active_coverage": _safe_div(active_periods, total_periods),
        "positive_active_ratio": _safe_div(int((active["net_profit"] > 0).sum()), active_periods),
        "full_total_trades": int(full_row.get("total_trades", 0)),
        "full_profit_factor": float(full_row.get("profit_factor", 0.0)),
        "full_net_profit": float(full_row.get("net_profit", 0.0)),
        "full_max_drawdown": float(full_row.get("max_drawdown", 0.0)),
    }


def _add_score_components(diagnostics: pd.DataFrame) -> pd.DataFrame:
    scored = diagnostics.copy()
    max_ratio = scored["profit_drawdown_ratio"].clip(lower=0).max()
    max_drawdown = scored["worst_period_drawdown"].clip(lower=0).max()

    scored["normalized_profit_drawdown_ratio"] = (
        scored["profit_drawdown_ratio"].clip(lower=0) / max_ratio
        if max_ratio > 0
        else 0.0
    )
    scored["coverage_penalty"] = (0.70 - scored["active_coverage"]).clip(lower=0)
    scored["profit_factor_penalty"] = (1.10 - scored["average_profit_factor"]).clip(lower=0)
    scored["drawdown_penalty"] = (
        0.25 * scored["worst_period_drawdown"].clip(lower=0) / max_drawdown
        if max_drawdown > 0
        else 0.0
    )
    scored["stability_score"] = (
        scored["positive_active_ratio"]
        + scored["normalized_profit_drawdown_ratio"]
        - scored["coverage_penalty"]
        - scored["profit_factor_penalty"]
        - scored["drawdown_penalty"]
    )

    return scored


def _finite_profit_factors(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator / denominator)


def _mean_or_zero(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    return float(values.mean())


def _median_or_zero(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    return float(values.median())
