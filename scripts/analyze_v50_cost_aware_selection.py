"""
Analyze V50 cost-aware sweep results.

This script prints research diagnostics only and does not promote a strategy.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy_lab.strategy_v50_candidates import FINAL_BALANCED_STRATEGY_NAME
from src.strategy_lab.strategy_v50_proxy_candidate import STRATEGY_NAME as PROXY_CANDIDATE_NAME
from src.strategy_lab.v50_cost_aware import DEFAULT_COST_AWARE_SWEEP_PATH


STRATEGY_COMPARISON_PATH = Path("reports/strategy_lab/strategy_comparison.csv")
DISPLAY_COLUMNS = [
    "source_variant",
    "variant_name",
    "cost_profile",
    "total_trades",
    "average_trades_per_day",
    "net_profit_factor",
    "net_profit",
    "max_drawdown",
    "profit_drawdown_ratio_net",
    "pf_without_top_5pct",
    "anti_overfit_pass",
]


def main() -> None:
    """Print cost-aware selection diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Cost-Aware Selection")
    print("=" * 72)

    sweep = _load_required_csv(DEFAULT_COST_AWARE_SWEEP_PATH)
    if sweep is None:
        print("Run first: python scripts/run_v50_cost_aware_sweep.py")
        return

    ranking = prepare_cost_aware_ranking(sweep)
    print("")
    _print_pick("Best without costs", best_for_profile(ranking, "cost_none"))
    _print_pick("Best cost_light", best_for_profile(ranking, "cost_light"))
    _print_pick("Best cost_medium", best_for_profile(ranking, "cost_medium"))
    _print_pick("Best cost_heavy", best_for_profile(ranking, "cost_heavy"))
    _print_pick("Best net profit/drawdown", best_profit_drawdown(ranking))
    _print_pick("Least dependent on top 5% trades", least_top_trade_dependency(ranking))

    print("")
    print("Cost-medium threshold checks:")
    medium = ranking[ranking["cost_profile"] == "cost_medium"].copy()
    pf_rows = medium[medium["net_profit_factor"] >= 1.20]
    dd_rows = medium[medium["max_drawdown"] <= 140]
    print(f"Rows with net PF >= 1.20: {len(pf_rows)}")
    print(f"Rows with DD <= 140: {len(dd_rows)}")
    if not pf_rows.empty:
        _print_table("PF >= 1.20 candidates", pf_rows.sort_values("net_profit_factor", ascending=False).head(10))
    if not dd_rows.empty:
        _print_table("DD <= 140 candidates", dd_rows.sort_values("profit_drawdown_ratio_net", ascending=False).head(10))

    print("")
    print("Reference comparison:")
    comparison = _load_optional_csv(STRATEGY_COMPARISON_PATH)
    if comparison is not None:
        references = comparison[
            comparison["strategy_name"].isin([PROXY_CANDIDATE_NAME, FINAL_BALANCED_STRATEGY_NAME])
        ].copy()
        if not references.empty:
            print(references.to_string(index=False))
        else:
            print("Reference rows not found in strategy_comparison.csv")
    else:
        print("strategy_comparison.csv not found; skipping clean-reference comparison.")

    print("")
    print("Paper trading recommendation:")
    print(build_cost_aware_recommendation(ranking))
    print("")
    print("No candidate was promoted automatically.")


def prepare_cost_aware_ranking(report: pd.DataFrame) -> pd.DataFrame:
    """Normalize sweep rows for ranking."""
    result = report.copy()
    required = set(DISPLAY_COLUMNS + ["gross_profit_factor", "gross_net_profit", "max_consecutive_losses"])
    missing = required.difference(result.columns)
    if missing:
        raise ValueError("cost-aware sweep missing columns: " + ", ".join(sorted(missing)))
    numeric = [
        "total_trades",
        "average_trades_per_day",
        "net_profit_factor",
        "net_profit",
        "max_drawdown",
        "profit_drawdown_ratio_net",
        "pf_without_top_5pct",
        "gross_profit_factor",
        "gross_net_profit",
        "max_consecutive_losses",
    ]
    for column in numeric:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0.0)
    result["anti_overfit_pass"] = result["anti_overfit_pass"].astype(bool)
    return result


def best_for_profile(ranking: pd.DataFrame, profile_name: str) -> pd.Series:
    """Return best row for one cost profile."""
    rows = ranking[ranking["cost_profile"] == profile_name].copy()
    if rows.empty:
        rows = ranking.copy()
    return _sort_cost_rows(_robust_or_all(rows)).iloc[0]


def best_profit_drawdown(ranking: pd.DataFrame) -> pd.Series:
    rows = ranking[ranking["cost_profile"] == "cost_medium"].copy()
    if rows.empty:
        rows = ranking
    rows = _robust_or_all(rows)
    return rows.sort_values(["profit_drawdown_ratio_net", "net_profit_factor"], ascending=False).iloc[0]


def least_top_trade_dependency(ranking: pd.DataFrame) -> pd.Series:
    rows = ranking[ranking["cost_profile"] == "cost_medium"].copy()
    if rows.empty:
        rows = ranking
    rows = _robust_or_all(rows)
    rows = rows.copy()
    rows["top5_pf_retention"] = rows["pf_without_top_5pct"] / rows["net_profit_factor"].where(
        rows["net_profit_factor"] != 0
    )
    rows["top5_pf_retention"] = rows["top5_pf_retention"].fillna(0.0)
    return rows.sort_values(["top5_pf_retention", "pf_without_top_5pct"], ascending=False).iloc[0]


def build_cost_aware_recommendation(ranking: pd.DataFrame) -> str:
    """Return cautious paper-trading recommendation text."""
    medium = ranking[ranking["cost_profile"] == "cost_medium"].copy()
    passing = medium[
        (medium["anti_overfit_pass"])
        & (medium["net_profit_factor"] >= 1.20)
        & (medium["max_drawdown"] <= 140)
        & (medium["pf_without_top_5pct"] >= 1.0)
    ].copy()
    if passing.empty:
        return (
            "No cost-aware variant clears all medium-cost robustness gates. Keep the proxy candidate research-only "
            "and focus next on reducing cost sensitivity before paper deployment."
        )
    row = _sort_cost_rows(passing).iloc[0]
    return (
        f"{row['source_variant']} / {row['variant_name']} is the strongest cost-aware research candidate under "
        "cost_medium. Keep it paper-only and verify with forward evidence before any promotion."
    )


def _sort_cost_rows(rows: pd.DataFrame) -> pd.DataFrame:
    return rows.sort_values(
        ["anti_overfit_pass", "net_profit_factor", "profit_drawdown_ratio_net", "net_profit"],
        ascending=[False, False, False, False],
    )


def _robust_or_all(rows: pd.DataFrame) -> pd.DataFrame:
    robust = rows[(rows["total_trades"] >= 700) & (rows["average_trades_per_day"] >= 0.70)].copy()
    return robust if not robust.empty else rows


def _print_pick(title: str, row: pd.Series) -> None:
    print("")
    print(title + ":")
    print(row[DISPLAY_COLUMNS].to_frame().T.to_string(index=False))


def _print_table(title: str, rows: pd.DataFrame) -> None:
    print("")
    print(title + ":")
    print(rows[DISPLAY_COLUMNS].to_string(index=False))


def _load_required_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        print(f"Missing report: {path}")
        return None
    print(f"Loaded report: {path}")
    return pd.read_csv(path)


def _load_optional_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path)


if __name__ == "__main__":
    main()
