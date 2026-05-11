"""
Counterfactual loss-filter sweep for the final V50 balanced candidate.

The sweep removes simulated trades matching loss-intelligence patterns. It is
research-only and does not execute trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.backtesting.metrics import calculate_metrics, metrics_to_dict
from src.strategy_lab.strategy_v50_candidates import FINAL_BALANCED_STRATEGY_NAME
from src.strategy_lab.v50_daily_coverage import build_daily_breakdown, build_daily_coverage_report
from src.strategy_lab.v50_loss_intelligence import (
    build_loss_breakdown,
    prepare_balanced_loss_trades,
)


DEFAULT_LOSS_FILTER_SWEEP_PATH = Path("reports/strategy_lab/v50_loss_filter_sweep.csv")
LOSS_FILTER_VARIANT_NAMES = (
    "loss_filter_base",
    "block_worst_hour",
    "block_worst_2_hours",
    "block_worst_weekday",
    "block_worst_session_side",
    "block_low_score_bucket",
    "block_bad_bars_in_trade_bucket",
    "block_after_1_loss_cooldown",
    "block_after_2_losses_cooldown",
    "balanced_loss_filter_combo",
    "strict_loss_filter_combo",
)
LOSS_FILTER_SWEEP_COLUMNS = [
    "strategy_name",
    "variant_name",
    "total_trades",
    "average_trades_per_day",
    "active_day_ratio",
    "win_rate",
    "profit_factor",
    "net_profit",
    "max_drawdown",
    "expectancy",
    "profit_drawdown_ratio",
    "max_consecutive_losses",
    "positive_months",
    "negative_months",
    "removed_trade_pct",
    "anti_overfit_pass",
]


@dataclass(frozen=True)
class LossFilterVariant:
    """One trade-level loss-filter variant."""

    variant_name: str
    blocked_hours: tuple[int, ...] = ()
    blocked_weekdays: tuple[str, ...] = ()
    blocked_session_sides: tuple[str, ...] = ()
    blocked_score_buckets: tuple[str, ...] = ()
    blocked_bars_buckets: tuple[str, ...] = ()
    cooldown_after_losses: int | None = None


def build_loss_filter_variants(trades: pd.DataFrame) -> list[LossFilterVariant]:
    """Build the requested loss-filter variants from the base trade report."""
    prepared = prepare_balanced_loss_trades(trades)
    worst_hours = tuple(_worst_values(prepared, "hour", limit=2))
    worst_hour = worst_hours[:1]
    worst_weekday = tuple(_worst_values(prepared, "weekday", limit=1))
    worst_session_side = tuple(_worst_values(prepared, "session_side", limit=1))
    worst_score_bucket = tuple(_worst_values(prepared, "score_bucket", limit=1))
    worst_bars_bucket = tuple(_worst_values(prepared, "bars_in_trade_bucket", limit=1))

    return [
        LossFilterVariant("loss_filter_base"),
        LossFilterVariant("block_worst_hour", blocked_hours=tuple(int(value) for value in worst_hour)),
        LossFilterVariant("block_worst_2_hours", blocked_hours=tuple(int(value) for value in worst_hours)),
        LossFilterVariant("block_worst_weekday", blocked_weekdays=worst_weekday),
        LossFilterVariant("block_worst_session_side", blocked_session_sides=worst_session_side),
        LossFilterVariant("block_low_score_bucket", blocked_score_buckets=worst_score_bucket),
        LossFilterVariant("block_bad_bars_in_trade_bucket", blocked_bars_buckets=worst_bars_bucket),
        LossFilterVariant("block_after_1_loss_cooldown", cooldown_after_losses=1),
        LossFilterVariant("block_after_2_losses_cooldown", cooldown_after_losses=2),
        LossFilterVariant(
            "balanced_loss_filter_combo",
            blocked_hours=tuple(int(value) for value in worst_hour),
            blocked_session_sides=worst_session_side,
            cooldown_after_losses=2,
        ),
        LossFilterVariant(
            "strict_loss_filter_combo",
            blocked_hours=tuple(int(value) for value in worst_hours),
            blocked_weekdays=worst_weekday,
            blocked_session_sides=worst_session_side,
            blocked_score_buckets=worst_score_bucket,
            blocked_bars_buckets=worst_bars_bucket,
            cooldown_after_losses=2,
        ),
    ]


def run_v50_loss_filter_sweep(
    trades: pd.DataFrame,
    market_data: pd.DataFrame | None = None,
    output_path: str | Path = DEFAULT_LOSS_FILTER_SWEEP_PATH,
) -> pd.DataFrame:
    """Run all loss-filter variants over simulated V50 balanced trades."""
    prepared = prepare_balanced_loss_trades(trades)
    variants = build_loss_filter_variants(prepared)
    rows = []
    base_row = None

    for variant in variants:
        filtered = apply_loss_filter_variant(prepared, variant)
        row = _sweep_row(variant, filtered, base_trade_count=len(prepared), market_data=market_data)
        if variant.variant_name == "loss_filter_base":
            base_row = row
            row["anti_overfit_pass"] = True
        else:
            row["anti_overfit_pass"] = _passes_anti_overfit(row, base_row or row)
        rows.append(row)

    report = pd.DataFrame(rows, columns=LOSS_FILTER_SWEEP_COLUMNS)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    return report


def apply_loss_filter_variant(trades: pd.DataFrame, variant: LossFilterVariant) -> pd.DataFrame:
    """Apply one loss-filter variant to a prepared trade report."""
    prepared = prepare_balanced_loss_trades(trades)
    if prepared.empty or variant.variant_name == "loss_filter_base":
        return prepared.reset_index(drop=True)

    mask = pd.Series(False, index=prepared.index)
    if variant.blocked_hours:
        mask |= prepared["hour"].isin(variant.blocked_hours)
    if variant.blocked_weekdays:
        mask |= prepared["weekday"].isin(variant.blocked_weekdays)
    if variant.blocked_session_sides:
        mask |= prepared["session_side"].isin(variant.blocked_session_sides)
    if variant.blocked_score_buckets:
        mask |= prepared["score_bucket"].isin(variant.blocked_score_buckets)
    if variant.blocked_bars_buckets:
        mask |= prepared["bars_in_trade_bucket"].isin(variant.blocked_bars_buckets)

    filtered = prepared.loc[~mask].copy().reset_index(drop=True)
    if variant.cooldown_after_losses is not None:
        filtered = _apply_loss_cooldown(filtered, variant.cooldown_after_losses)

    return filtered.reset_index(drop=True)


def sort_loss_filter_sweep(report: pd.DataFrame) -> pd.DataFrame:
    """Sort variants by anti-overfit pass, PF, and drawdown."""
    prepared = report.copy()
    for column in ["profit_factor", "profit_drawdown_ratio", "net_profit", "max_drawdown"]:
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce").fillna(0.0)
    return prepared.sort_values(
        ["anti_overfit_pass", "profit_factor", "profit_drawdown_ratio", "net_profit", "max_drawdown"],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)


def _sweep_row(
    variant: LossFilterVariant,
    trades: pd.DataFrame,
    base_trade_count: int,
    market_data: pd.DataFrame | None,
) -> dict:
    metrics = calculate_metrics(trades, initial_balance=1000.0)
    metrics_dict = metrics_to_dict(metrics)
    max_drawdown = float(metrics_dict["max_drawdown"])
    net_profit = float(metrics_dict["net_profit"])
    coverage = _coverage_row(trades, market_data)
    months = _monthly_pnl(trades)

    return {
        "strategy_name": FINAL_BALANCED_STRATEGY_NAME,
        "variant_name": variant.variant_name,
        "total_trades": metrics_dict["total_trades"],
        "average_trades_per_day": float(coverage.get("average_trades_per_day", 0.0)),
        "active_day_ratio": float(coverage.get("active_day_ratio", 0.0)),
        "win_rate": metrics_dict["win_rate"],
        "profit_factor": metrics_dict["profit_factor"],
        "net_profit": net_profit,
        "max_drawdown": max_drawdown,
        "expectancy": metrics_dict["expectancy"],
        "profit_drawdown_ratio": net_profit / max_drawdown if max_drawdown > 0 else 0.0,
        "max_consecutive_losses": metrics_dict["max_consecutive_losses"],
        "positive_months": int((months > 0).sum()) if not months.empty else 0,
        "negative_months": int((months < 0).sum()) if not months.empty else 0,
        "removed_trade_pct": (base_trade_count - int(metrics_dict["total_trades"])) / base_trade_count
        if base_trade_count
        else 0.0,
        "anti_overfit_pass": False,
    }


def _passes_anti_overfit(row: dict, base_row: dict) -> bool:
    return bool(
        int(row["total_trades"]) >= 700
        and float(row["average_trades_per_day"]) >= 0.75
        and float(row["profit_factor"]) >= float(base_row["profit_factor"])
        and float(row["max_drawdown"]) <= float(base_row["max_drawdown"])
        and int(row["max_consecutive_losses"]) < int(base_row["max_consecutive_losses"])
        and float(row["net_profit"]) > 0
        and float(row["removed_trade_pct"]) <= 0.40
    )


def _coverage_row(trades: pd.DataFrame, market_data: pd.DataFrame | None) -> dict:
    if trades.empty:
        return {}
    daily_breakdown = build_daily_breakdown(
        trades,
        strategy_names=(FINAL_BALANCED_STRATEGY_NAME,),
        market_data=market_data,
    )
    coverage = build_daily_coverage_report(daily_breakdown)
    if coverage.empty:
        return {}
    return coverage.iloc[0].to_dict()


def _monthly_pnl(trades: pd.DataFrame) -> pd.Series:
    if trades.empty or "entry_time" not in trades.columns:
        return pd.Series(dtype=float)
    prepared = trades.copy()
    prepared["entry_time"] = pd.to_datetime(prepared["entry_time"], errors="coerce")
    prepared = prepared.dropna(subset=["entry_time"])
    if prepared.empty:
        return pd.Series(dtype=float)
    prepared["month"] = prepared["entry_time"].dt.to_period("M").astype("string")
    return prepared.groupby("month")["pnl"].sum()


def _apply_loss_cooldown(trades: pd.DataFrame, cooldown_after_losses: int) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()

    kept_rows = []
    consecutive_losses = 0
    for _, row in trades.sort_values("entry_time").iterrows():
        if consecutive_losses >= cooldown_after_losses:
            consecutive_losses = 0
            continue

        kept_rows.append(row)
        if float(row["pnl"]) < 0:
            consecutive_losses += 1
        else:
            consecutive_losses = 0

    return pd.DataFrame(kept_rows, columns=trades.columns)


def _worst_values(trades: pd.DataFrame, column: str, limit: int) -> list:
    if trades.empty or column not in trades.columns:
        return []

    grouped = trades.groupby(column, dropna=False)["pnl"].agg(["count", "sum"]).reset_index()
    min_count = max(3, int(len(trades) * 0.01))
    grouped = grouped[grouped["count"] >= min_count]
    if grouped.empty:
        return []
    return grouped.sort_values(["sum", "count"], ascending=[True, False])[column].head(limit).tolist()
