"""
Analyze V50 Axi real-cost report.

The script prints paper-trading diagnostics only. It does not promote any
strategy automatically.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy_lab.strategy_v50_proxy_candidate import STRATEGY_NAME as PROXY_CANDIDATE_NAME
from src.strategy_lab.v50_cost_aware import DEFAULT_AXI_REAL_COST_BACKTEST_PATH


DISPLAY_COLUMNS = [
    "strategy_name",
    "cost_profile",
    "total_trades",
    "average_trades_per_day",
    "net_profit_factor",
    "net_profit_after_costs",
    "average_cost_per_trade",
    "average_trade_after_costs",
    "max_drawdown_after_costs",
    "profit_drawdown_ratio_after_costs",
]


def main() -> None:
    """Print Axi real-cost selection diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Axi Real-Cost Selection")
    print("=" * 72)

    report = _load_required_csv(DEFAULT_AXI_REAL_COST_BACKTEST_PATH)
    if report is None:
        print("Run first: python scripts/run_v50_axi_real_cost_backtest.py")
        return
    ranking = prepare_axi_real_cost_ranking(report)

    print("")
    _print_pick("Best axi_pro_realistic", best_for_profile(ranking, "axi_pro_realistic"))
    _print_pick("Best axi_pro_conservative", best_for_profile(ranking, "axi_pro_conservative"))

    proxy_realistic = row_for_strategy_profile(ranking, PROXY_CANDIDATE_NAME, "axi_pro_realistic")
    proxy_conservative = row_for_strategy_profile(ranking, PROXY_CANDIDATE_NAME, "axi_pro_conservative")
    legacy_medium = row_for_strategy_profile(ranking, PROXY_CANDIDATE_NAME, "cost_medium")

    print("")
    print("Proxy threshold checks:")
    print(f"Proxy net PF >= 1.20 with Axi realistic: {bool(proxy_realistic['net_profit_factor'] >= 1.20)}")
    print(f"Proxy net PF >= 1.20 with Axi conservative: {bool(proxy_conservative['net_profit_factor'] >= 1.20)}")

    print("")
    print("Axi real cost vs old cost_medium for proxy:")
    comparison = pd.DataFrame([proxy_realistic, proxy_conservative, legacy_medium])[DISPLAY_COLUMNS]
    print(comparison.to_string(index=False))

    print("")
    print("Real-cost margin:")
    print(
        f"Proxy realistic average cost/trade: {proxy_realistic['average_cost_per_trade']:.4f} EUR; "
        f"average net trade: {proxy_realistic['average_trade_after_costs']:.4f} EUR"
    )
    print(
        f"Proxy conservative average cost/trade: {proxy_conservative['average_cost_per_trade']:.4f} EUR; "
        f"average net trade: {proxy_conservative['average_trade_after_costs']:.4f} EUR"
    )

    print("")
    print("Paper trading recommendation:")
    print(build_axi_real_cost_recommendation(ranking))
    print("")
    print("No candidate was promoted automatically.")


def prepare_axi_real_cost_ranking(report: pd.DataFrame) -> pd.DataFrame:
    """Normalize Axi real-cost rows."""
    result = report.copy()
    missing = set(DISPLAY_COLUMNS).difference(result.columns)
    if missing:
        raise ValueError("Axi real-cost report missing columns: " + ", ".join(sorted(missing)))
    numeric = [column for column in DISPLAY_COLUMNS if column not in {"strategy_name", "cost_profile"}]
    for column in numeric:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0.0)
    return result


def best_for_profile(ranking: pd.DataFrame, profile_name: str) -> pd.Series:
    """Return best row for a cost profile."""
    rows = ranking[ranking["cost_profile"] == profile_name].copy()
    if rows.empty:
        raise ValueError(f"Missing profile in Axi report: {profile_name}")
    robust = rows[(rows["total_trades"] >= 700) & (rows["average_trades_per_day"] >= 0.70)]
    if not robust.empty:
        rows = robust
    return rows.sort_values(
        ["net_profit_factor", "profit_drawdown_ratio_after_costs", "net_profit_after_costs"],
        ascending=False,
    ).iloc[0]


def row_for_strategy_profile(ranking: pd.DataFrame, strategy_name: str, profile_name: str) -> pd.Series:
    """Return one strategy/profile row."""
    rows = ranking[(ranking["strategy_name"] == strategy_name) & (ranking["cost_profile"] == profile_name)]
    if rows.empty:
        raise ValueError(f"Missing row for {strategy_name} / {profile_name}")
    return rows.iloc[0]


def build_axi_real_cost_recommendation(ranking: pd.DataFrame) -> str:
    """Return cautious paper-trading recommendation text."""
    realistic = ranking[ranking["cost_profile"] == "axi_pro_realistic"].copy()
    conservative = ranking[ranking["cost_profile"] == "axi_pro_conservative"].copy()
    robust_realistic = realistic[
        (realistic["total_trades"] >= 700)
        & (realistic["net_profit_factor"] >= 1.20)
        & (realistic["net_profit_after_costs"] > 0)
    ]
    robust_conservative = conservative[
        (conservative["total_trades"] >= 700)
        & (conservative["net_profit_factor"] >= 1.20)
        & (conservative["net_profit_after_costs"] > 0)
    ]
    if robust_realistic.empty:
        return "No strategy clears the Axi realistic net PF gate. Keep all candidates research-only."
    best = best_for_profile(ranking, "axi_pro_realistic")
    if robust_conservative.empty:
        return (
            f"{best['strategy_name']} clears the realistic-cost gate, but not the conservative-cost gate. "
            "Use only a paper-trading study, with no automatic promotion."
        )
    conservative_best = best_for_profile(ranking, "axi_pro_conservative")
    return (
        f"{conservative_best['strategy_name']} is the strongest Axi-cost paper-trading research candidate. "
        "No automatic promotion; verify forward fills and broker statements first."
    )


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
