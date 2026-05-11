"""
Analyze realtime-safe V50 loss proxy sweep results.

The report compares realtime variants with the base strategy and with the
diagnostic bars-in-trade counterfactual. It does not promote any variant.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy_lab.v50_loss_filter_sweep import DEFAULT_LOSS_FILTER_SWEEP_PATH
from src.strategy_lab.v50_realtime_loss_proxy_sweep import DEFAULT_REALTIME_LOSS_PROXY_SWEEP_PATH


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
    """Print realtime proxy selection diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Realtime Proxy Selection")
    print("=" * 72)

    sweep = _load_required_csv(DEFAULT_REALTIME_LOSS_PROXY_SWEEP_PATH)
    if sweep is None:
        print("Run first: python scripts/run_v50_realtime_loss_proxy_sweep.py")
        return

    diagnostic = _load_optional_csv(DEFAULT_LOSS_FILTER_SWEEP_PATH)
    ranking = prepare_realtime_proxy_ranking(sweep)
    base = base_row(ranking)

    print("")
    print("Comparison against v50_final_balanced_strategy:")
    print(base[DISPLAY_COLUMNS].to_frame().T.to_string(index=False))

    print("")
    print("Comparison against diagnostic block_bad_bars_in_trade_bucket:")
    _print_diagnostic_comparison(diagnostic)

    _print_pick("Best tradable profit factor", select_best_profit_factor(ranking))
    _print_pick("Best tradable drawdown", select_best_drawdown(ranking))
    _print_pick("Best tradable profit/drawdown", select_best_profit_drawdown(ranking))
    _print_pick("Best tradable max loss streak", select_best_loss_streak(ranking))
    _print_pick("Best quality/coverage compromise", select_best_quality_coverage(ranking))

    print("")
    print("Threshold checks:")
    print(f"PF >= 1.25 with >= 0.75 trade/day: {exists_pf_with_frequency(ranking, 1.25, 0.75)}")
    print(f"PF >= 1.30 without leakage: {exists_pf_no_leakage(ranking, 1.30)}")
    print(f"DD below 135 with PF >= base: {exists_dd_below_with_base_pf(ranking, base, 135.0)}")

    print("")
    print("No variant was promoted automatically.")


def prepare_realtime_proxy_ranking(sweep: pd.DataFrame) -> pd.DataFrame:
    """Normalize sweep report for selection."""
    required = set(DISPLAY_COLUMNS + ["leakage_safe"])
    missing = required.difference(sweep.columns)
    if missing:
        raise ValueError("realtime proxy sweep missing columns: " + ", ".join(sorted(missing)))

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
    result["leakage_safe"] = result["leakage_safe"].astype(bool)
    return result


def base_row(ranking: pd.DataFrame) -> pd.Series:
    base = ranking[ranking["variant_name"] == "proxy_base"]
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


def select_best_loss_streak(ranking: pd.DataFrame) -> pd.Series:
    eligible = _eligible_or_all(ranking)
    return eligible.sort_values(["max_consecutive_losses", "profit_factor"], ascending=[True, False]).iloc[0]


def select_best_quality_coverage(ranking: pd.DataFrame) -> pd.Series:
    eligible = ranking[ranking["anti_overfit_pass"] & ranking["leakage_safe"]].copy()
    if eligible.empty:
        eligible = _eligible_or_all(ranking)
    return eligible.sort_values(
        ["profit_drawdown_ratio", "profit_factor", "average_trades_per_day"],
        ascending=False,
    ).iloc[0]


def exists_pf_with_frequency(ranking: pd.DataFrame, min_pf: float, min_average: float) -> bool:
    return bool(
        (
            (ranking["profit_factor"] >= min_pf)
            & (ranking["average_trades_per_day"] >= min_average)
            & ranking["leakage_safe"]
        ).any()
    )


def exists_pf_no_leakage(ranking: pd.DataFrame, min_pf: float) -> bool:
    return bool(((ranking["profit_factor"] >= min_pf) & ranking["leakage_safe"]).any())


def exists_dd_below_with_base_pf(ranking: pd.DataFrame, base: pd.Series, max_dd: float) -> bool:
    return bool(
        (
            (ranking["max_drawdown"] < max_dd)
            & (ranking["profit_factor"] >= float(base["profit_factor"]))
            & ranking["leakage_safe"]
        ).any()
    )


def _eligible_or_all(ranking: pd.DataFrame) -> pd.DataFrame:
    eligible = ranking[
        (ranking["total_trades"] >= 700)
        & (ranking["average_trades_per_day"] >= 0.75)
        & ranking["leakage_safe"]
    ].copy()
    return eligible if not eligible.empty else ranking[ranking["leakage_safe"]].copy()


def _print_pick(title: str, row: pd.Series) -> None:
    print("")
    print(title + ":")
    print(row[DISPLAY_COLUMNS].to_frame().T.to_string(index=False))


def _print_diagnostic_comparison(diagnostic: pd.DataFrame | None) -> None:
    if diagnostic is None or diagnostic.empty or "variant_name" not in diagnostic.columns:
        print("(diagnostic report not found)")
        return
    row = diagnostic[diagnostic["variant_name"] == "block_bad_bars_in_trade_bucket"]
    if row.empty:
        print("(diagnostic variant not found)")
        return
    print(row[DISPLAY_COLUMNS].to_string(index=False))


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
