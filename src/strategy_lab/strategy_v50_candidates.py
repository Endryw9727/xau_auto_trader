"""
Official V50 edge-filter strategy candidates for Strategy Lab.

These candidates wrap v50_pine_technical_strategy with simple research filters
derived from trade-level diagnostics. They do not perform execution.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.strategy_lab import strategy_v50_pine
from src.strategy_lab.strategy_diagnostics import build_strategy_diagnostics
from src.strategy_lab.v50_edge_filters import (
    V50EdgeFilterVariant,
    make_v50_edge_filter_signal_generator,
)


LOW_RISK_LONDON_STRATEGY_NAME = "v50_low_risk_london_strategy"
BALANCED_NO_ASIA_LONDON_STRATEGY_NAME = "v50_balanced_no_asia_london_strategy"
GROWTH_LONG_ALL_SHORT_LONDON_STRATEGY_NAME = "v50_growth_long_all_short_london_strategy"

OFFICIAL_CANDIDATE_STRATEGY_NAMES = (
    LOW_RISK_LONDON_STRATEGY_NAME,
    BALANCED_NO_ASIA_LONDON_STRATEGY_NAME,
    GROWTH_LONG_ALL_SHORT_LONDON_STRATEGY_NAME,
)
V50_CANDIDATE_STRATEGY_NAMES = (
    strategy_v50_pine.STRATEGY_NAME,
    *OFFICIAL_CANDIDATE_STRATEGY_NAMES,
)
V50_CANDIDATE_COMPARISON_PATH = Path("reports/strategy_lab/v50_candidate_comparison.csv")
V50_CANDIDATE_WALK_FORWARD_QUARTER_PATH = Path("reports/strategy_lab/v50_candidate_walk_forward_quarter.csv")
V50_CANDIDATE_WALK_FORWARD_MONTH_PATH = Path("reports/strategy_lab/v50_candidate_walk_forward_month.csv")
V50_CANDIDATE_EDGES_PATH = Path("reports/strategy_lab/v50_candidate_edges.csv")

LOW_RISK_LONDON_VARIANT = V50EdgeFilterVariant(
    LOW_RISK_LONDON_STRATEGY_NAME,
    allowed_sessions=("LONDON",),
)
BALANCED_NO_ASIA_LONDON_VARIANT = V50EdgeFilterVariant(
    BALANCED_NO_ASIA_LONDON_STRATEGY_NAME,
    allowed_sides=("BUY",),
    blocked_sessions=("ASIA/LONDON",),
)
GROWTH_LONG_ALL_SHORT_LONDON_VARIANT = V50EdgeFilterVariant(
    GROWTH_LONG_ALL_SHORT_LONDON_STRATEGY_NAME,
    short_allowed_sessions=("LONDON",),
)

generate_low_risk_london_signal = make_v50_edge_filter_signal_generator(LOW_RISK_LONDON_VARIANT)
generate_balanced_no_asia_london_signal = make_v50_edge_filter_signal_generator(BALANCED_NO_ASIA_LONDON_VARIANT)
generate_growth_long_all_short_london_signal = make_v50_edge_filter_signal_generator(
    GROWTH_LONG_ALL_SHORT_LONDON_VARIANT
)


def export_v50_candidate_comparison(
    comparison: pd.DataFrame,
    output_path: str | Path = V50_CANDIDATE_COMPARISON_PATH,
) -> Path:
    """Export the Strategy Lab comparison rows for V50 technical candidates."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    filtered = comparison[comparison["strategy_name"].isin(V50_CANDIDATE_STRATEGY_NAMES)].copy()
    filtered.to_csv(output_path, index=False)
    return output_path


def export_v50_candidate_walk_forward(
    analysis: pd.DataFrame,
    period: str,
    output_path: str | Path | None = None,
) -> Path:
    """Export a diagnostics summary for V50 candidates in one walk-forward period mode."""
    if output_path is None:
        output_path = _walk_forward_path_for_period(period)

    diagnostics = build_strategy_diagnostics(
        walk_forward=analysis,
        strategy_names=V50_CANDIDATE_STRATEGY_NAMES,
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(output_path, index=False)
    return output_path


def _walk_forward_path_for_period(period: str) -> Path:
    if period == "quarter":
        return V50_CANDIDATE_WALK_FORWARD_QUARTER_PATH
    if period == "month":
        return V50_CANDIDATE_WALK_FORWARD_MONTH_PATH
    return Path(f"reports/strategy_lab/v50_candidate_walk_forward_{period}.csv")
