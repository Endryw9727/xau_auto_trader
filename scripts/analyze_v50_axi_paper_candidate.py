"""
Analyze Axi Pro paper/equity simulation results.

The output is a research recommendation only. No strategy is promoted
automatically.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy_lab.v50_axi_equity import (
    DEFAULT_AXI_EQUITY_SIMULATION_PATH,
    DEFAULT_AXI_MONTHLY_EQUITY_PATH,
)


DISPLAY_COLUMNS = [
    "strategy_name",
    "scenario",
    "ending_equity",
    "net_profit_eur",
    "max_drawdown_eur",
    "max_drawdown_percent",
    "total_trades",
    "trades_per_day",
    "profit_factor_net",
    "average_trade_eur",
    "average_loss_eur",
    "max_consecutive_losses",
    "time_to_2000_if_reached",
    "trades_to_2000_if_reached",
    "lot_max",
]


def main() -> None:
    """Print paper-candidate diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Axi Paper Candidate")
    print("=" * 72)

    summary = _load_required_csv(DEFAULT_AXI_EQUITY_SIMULATION_PATH)
    monthly = _load_required_csv(DEFAULT_AXI_MONTHLY_EQUITY_PATH)
    if summary is None or monthly is None:
        print("Run first: python scripts/run_v50_axi_equity_simulation.py")
        return
    ranking = prepare_paper_candidate_ranking(summary)

    best = best_paper_candidate(ranking)
    print("")
    print("Best paper candidate:")
    print(best[DISPLAY_COLUMNS].to_frame().T.to_string(index=False))

    print("")
    print("proxy_hardened_score_plus vs proxy_hardened_no_worst_hours:")
    comparison = ranking[
        ranking["strategy_name"].isin(["proxy_hardened_score_plus", "proxy_hardened_no_worst_hours"])
        & (ranking["scenario"] == "axi_realistic_slippage_0_0")
    ]
    print(comparison[DISPLAY_COLUMNS].to_string(index=False))

    print("")
    print("Risk checks:")
    print(f"Drawdown acceptable with 1000 EUR / 0.01 lots: {is_drawdown_acceptable(best)}")
    print(f"Estimated average trade risk: {abs(best['average_loss_eur']):.2f} EUR average losing trade")
    print(f"Worst month: {best['worst_month']:.2f} EUR")
    print(f"Max consecutive losses: {int(best['max_consecutive_losses'])}")
    if pd.notna(best["time_to_2000_if_reached"]):
        print(
            "Reached 2000 EUR: yes, after "
            f"{int(best['trades_to_2000_if_reached'])} trades / {int(best['time_to_2000_if_reached'])} days"
        )
    else:
        print("Reached 2000 EUR: no")

    print("")
    print("Paper trading recommendation:")
    print(build_paper_recommendation(best))
    print("")
    print("No candidate was promoted automatically.")


def prepare_paper_candidate_ranking(summary: pd.DataFrame) -> pd.DataFrame:
    """Normalize summary rows for ranking."""
    result = summary.copy()
    missing = set(DISPLAY_COLUMNS + ["worst_month"]).difference(result.columns)
    if missing:
        raise ValueError("Axi equity summary missing columns: " + ", ".join(sorted(missing)))
    numeric = [column for column in DISPLAY_COLUMNS if column not in {"strategy_name", "scenario"}] + ["worst_month"]
    for column in numeric:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def best_paper_candidate(ranking: pd.DataFrame) -> pd.Series:
    """Return strongest realistic-scenario paper candidate."""
    realistic = ranking[ranking["scenario"] == "axi_realistic_slippage_0_0"].copy()
    if realistic.empty:
        realistic = ranking.copy()
    robust = realistic[
        (realistic["total_trades"] >= 700)
        & (realistic["profit_factor_net"] >= 1.20)
        & (realistic["net_profit_eur"] > 0)
    ].copy()
    if not robust.empty:
        realistic = robust
    return realistic.sort_values(
        ["profit_factor_net", "max_drawdown_percent", "net_profit_eur"],
        ascending=[False, True, False],
    ).iloc[0]


def is_drawdown_acceptable(row: pd.Series, max_drawdown_percent: float = 20.0) -> bool:
    """Return True when drawdown is inside a paper-study threshold."""
    return bool(float(row["max_drawdown_percent"]) <= max_drawdown_percent)


def build_paper_recommendation(row: pd.Series) -> str:
    """Return cautious paper-trading yes/no text."""
    if (
        float(row["profit_factor_net"]) >= 1.20
        and float(row["net_profit_eur"]) > 0
        and is_drawdown_acceptable(row)
        and int(row["max_consecutive_losses"]) <= 12
    ):
        return (
            f"Paper trading: yes, as a controlled research study for {row['strategy_name']}. "
            "Use demo/paper only, verify fills and costs, and do not promote automatically."
        )
    return "Paper trading: no. The simulated equity profile is not robust enough yet."


def _load_required_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        print(f"Missing report: {path}")
        return None
    print(f"Loaded report: {path}")
    return pd.read_csv(path)


if __name__ == "__main__":
    main()
