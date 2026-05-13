"""
Analyze dynamic defensive paper-mode selection.

The output is advisory for paper mode only. It does not edit config or enable
live trading.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.paper.defensive_mode_engine import (
    DEFAULT_DYNAMIC_DEFENSIVE_SUMMARY_PATH,
    VARIANT_DYNAMIC,
    VARIANT_DYNAMIC_NY18,
    VARIANT_HIGH_MARGIN_ALWAYS,
    VARIANT_MAIN_ALWAYS,
)


def main() -> None:
    """Print dynamic defensive selection diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - Dynamic Defensive Selection")
    print("=" * 72)
    print("Mode: paper/research advisory only")

    if not DEFAULT_DYNAMIC_DEFENSIVE_SUMMARY_PATH.exists():
        print(f"Missing report: {DEFAULT_DYNAMIC_DEFENSIVE_SUMMARY_PATH}")
        print("Run first: python scripts/run_dynamic_defensive_paper_simulation.py")
        return

    summary = prepare_summary(pd.read_csv(DEFAULT_DYNAMIC_DEFENSIVE_SUMMARY_PATH))
    main_row = row_for_variant(summary, VARIANT_MAIN_ALWAYS)
    high_row = row_for_variant(summary, VARIANT_HIGH_MARGIN_ALWAYS)
    dynamic_row = row_for_variant(summary, VARIANT_DYNAMIC)
    research_row = row_for_variant(summary, VARIANT_DYNAMIC_NY18)

    print("")
    print("Comparison:")
    print(
        summary[
            [
                "variant_name",
                "total_trades",
                "trades_per_day",
                "profit_factor_net",
                "ending_equity",
                "max_drawdown_pct",
                "max_consecutive_losses",
                "profit_factor_last_30",
                "profit_factor_last_50",
                "profit_factor_last_100",
            ]
        ].to_string(index=False)
    )

    print("")
    print("Dynamic vs main:")
    print(f"  Improves PF: {dynamic_row['profit_factor_net'] > main_row['profit_factor_net']}")
    print(f"  Improves ending equity: {dynamic_row['ending_equity'] > main_row['ending_equity']}")
    print(f"  Reduces DD: {dynamic_row['max_drawdown_pct'] < main_row['max_drawdown_pct']}")
    print(f"  Reduces PF degradation last 30: {dynamic_row['profit_factor_last_30'] > main_row['profit_factor_last_30']}")
    print(f"  Reduces PF degradation last 50: {dynamic_row['profit_factor_last_50'] > main_row['profit_factor_last_50']}")
    print(f"  Reduces max loss streak: {dynamic_row['max_consecutive_losses'] < main_row['max_consecutive_losses']}")
    print(f"  Keeps >= 0.50 trades/day: {dynamic_row['trades_per_day'] >= 0.50}")

    print("")
    print("Dynamic vs high-margin:")
    print(f"  Improves PF: {dynamic_row['profit_factor_net'] > high_row['profit_factor_net']}")
    print(f"  Improves ending equity: {dynamic_row['ending_equity'] > high_row['ending_equity']}")
    print(f"  Reduces DD: {dynamic_row['max_drawdown_pct'] < high_row['max_drawdown_pct']}")
    print(f"  Keeps >= 0.50 trades/day: {dynamic_row['trades_per_day'] >= 0.50}")

    print("")
    print("Research NY hour-18 filter:")
    print(
        f"  PF {research_row['profit_factor_net']:.3f}, DD {research_row['max_drawdown_pct']:.2f}%, "
        f"trades/day {research_row['trades_per_day']:.3f}"
    )

    print("")
    print("Recommended paper mode:")
    print(recommend_mode(main_row, high_row, dynamic_row, research_row))
    print("")
    print("allow_live remains false. No strategy was promoted automatically.")


def prepare_summary(summary: pd.DataFrame) -> pd.DataFrame:
    """Normalize numeric summary columns."""
    result = summary.copy()
    for column in result.columns:
        if column not in {"variant_name"}:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def row_for_variant(summary: pd.DataFrame, variant_name: str) -> pd.Series:
    """Return one variant row."""
    match = summary[summary["variant_name"] == variant_name]
    if match.empty:
        raise ValueError(f"Missing dynamic defensive variant: {variant_name}")
    return match.iloc[0]


def recommend_mode(main_row: pd.Series, high_row: pd.Series, dynamic_row: pd.Series, research_row: pd.Series) -> str:
    """Return a cautious paper recommendation without changing configuration."""
    dynamic_good = (
        dynamic_row["profit_factor_net"] >= main_row["profit_factor_net"]
        and dynamic_row["max_drawdown_pct"] <= main_row["max_drawdown_pct"]
        and dynamic_row["trades_per_day"] >= 0.50
    )
    high_good = high_row["max_drawdown_pct"] < main_row["max_drawdown_pct"] and high_row["profit_factor_net"] >= main_row["profit_factor_net"]
    if dynamic_good:
        return "Use dynamic NORMAL/DEFENSIVE/PAUSE for paper study only; keep high-margin as fallback."
    if high_good:
        return "Use DEFENSIVE high-margin for paper study only; dynamic needs more evidence."
    return "Pause paper expansion; continue diagnostics before changing paper mode."


if __name__ == "__main__":
    main()
