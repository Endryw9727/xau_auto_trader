"""
Trade-level diagnostics for backtest reports.

The helpers in this module operate only on already exported trade DataFrames.
"""

from __future__ import annotations

import pandas as pd

from src.backtesting.metrics import calculate_max_consecutive
from src.analysis.session_analysis import classify_hour_to_session


TRADE_LEVEL_SUMMARY_COLUMNS = [
    "strategy_name",
    "total_trades",
    "wins",
    "losses",
    "win_rate",
    "gross_profit",
    "gross_loss",
    "profit_factor",
    "average_trade",
    "median_trade",
    "best_trade",
    "worst_trade",
    "max_consecutive_losses",
    "average_bars_in_trade",
]
GROUP_SUMMARY_COLUMNS = [
    "group",
    "total_trades",
    "wins",
    "losses",
    "win_rate",
    "net_profit",
    "profit_factor",
    "average_trade",
]


def prepare_trade_report(trades: pd.DataFrame) -> pd.DataFrame:
    """Normalize optional trade report columns for diagnostics."""
    result = trades.copy()

    if "pnl" not in result.columns and "profit_loss" in result.columns:
        result["pnl"] = result["profit_loss"]
    if "profit_loss" not in result.columns and "pnl" in result.columns:
        result["profit_loss"] = result["pnl"]
    if "entry_time" not in result.columns and "timestamp_open" in result.columns:
        result["entry_time"] = result["timestamp_open"]
    if "exit_time" not in result.columns and "timestamp_close" in result.columns:
        result["exit_time"] = result["timestamp_close"]

    if "pnl" in result.columns:
        result["pnl"] = pd.to_numeric(result["pnl"], errors="coerce").fillna(0.0)
        result["profit_loss"] = result["pnl"]

    if "entry_time" in result.columns:
        result["entry_time"] = pd.to_datetime(result["entry_time"], errors="coerce")

    if "exit_time" in result.columns:
        result["exit_time"] = pd.to_datetime(result["exit_time"], errors="coerce")

    if "side_label" not in result.columns and "side" in result.columns:
        result["side_label"] = result["side"].apply(_side_label)

    if "session" not in result.columns and "entry_time" in result.columns:
        result["session"] = result["entry_time"].dt.hour.apply(
            lambda hour: classify_hour_to_session(int(hour)) if pd.notna(hour) else "Unknown"
        )

    if "bars_in_trade" in result.columns:
        result["bars_in_trade"] = pd.to_numeric(result["bars_in_trade"], errors="coerce")

    return result


def has_strategy_trade_data(trades: pd.DataFrame | None) -> bool:
    """Return True when a trade DataFrame supports per-strategy diagnostics."""
    return trades is not None and "strategy_name" in trades.columns and ("pnl" in trades.columns or "profit_loss" in trades.columns)


def build_trade_level_summary(
    trades: pd.DataFrame,
    strategy_names: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Summarize trade-level performance for each strategy."""
    prepared = prepare_trade_report(trades)

    if not has_strategy_trade_data(prepared):
        return pd.DataFrame(columns=TRADE_LEVEL_SUMMARY_COLUMNS)

    if strategy_names is not None:
        prepared = prepared[prepared["strategy_name"].isin(strategy_names)]

    rows = [
        _summary_row(strategy_name, group)
        for strategy_name, group in prepared.groupby("strategy_name", sort=True)
    ]
    return pd.DataFrame(rows, columns=TRADE_LEVEL_SUMMARY_COLUMNS)


def summarize_strategy_group(
    trades: pd.DataFrame,
    strategy_name: str,
    group_column: str,
) -> pd.DataFrame:
    """Build a grouped P&L table for one strategy."""
    prepared = prepare_trade_report(trades)
    if not has_strategy_trade_data(prepared):
        return pd.DataFrame(columns=GROUP_SUMMARY_COLUMNS)

    strategy_trades = prepared[prepared["strategy_name"] == strategy_name].copy()
    if strategy_trades.empty or group_column not in strategy_trades.columns:
        return pd.DataFrame(columns=GROUP_SUMMARY_COLUMNS)

    strategy_trades[group_column] = strategy_trades[group_column].astype("object").where(
        strategy_trades[group_column].notna(),
        "Unknown",
    )
    rows = [
        {"group": group_value, **_pnl_stats(group["pnl"])}
        for group_value, group in strategy_trades.groupby(group_column, dropna=False)
    ]
    return pd.DataFrame(rows, columns=GROUP_SUMMARY_COLUMNS).sort_values(
        ["net_profit", "total_trades"],
        ascending=[False, False],
    ).reset_index(drop=True)


def add_time_buckets(trades: pd.DataFrame) -> pd.DataFrame:
    """Add year and month buckets from entry_time when available."""
    prepared = prepare_trade_report(trades)
    if "entry_time" not in prepared.columns:
        return prepared

    prepared["year"] = prepared["entry_time"].dt.year.astype("Int64").astype("string")
    prepared["month"] = prepared["entry_time"].dt.to_period("M").astype("string")
    return prepared


def find_loss_clusters(
    trades: pd.DataFrame,
    strategy_name: str,
    min_losses: int = 3,
) -> pd.DataFrame:
    """Find consecutive losing-trade clusters for one strategy."""
    prepared = prepare_trade_report(trades)
    if not has_strategy_trade_data(prepared):
        return _empty_loss_clusters()

    strategy_trades = prepared[prepared["strategy_name"] == strategy_name].copy()
    if strategy_trades.empty:
        return _empty_loss_clusters()

    if "entry_time" in strategy_trades.columns:
        strategy_trades = strategy_trades.sort_values("entry_time")

    clusters = []
    current = []

    for _, row in strategy_trades.iterrows():
        if float(row["pnl"]) < 0:
            current.append(row)
            continue

        _append_loss_cluster(clusters, current, min_losses)
        current = []

    _append_loss_cluster(clusters, current, min_losses)
    return pd.DataFrame(
        clusters,
        columns=[
            "start_time",
            "end_time",
            "loss_count",
            "net_loss",
            "worst_trade",
        ],
    )


def build_numeric_observations(trades: pd.DataFrame, strategy_name: str) -> list[str]:
    """Create simple numerical observations without changing any strategy."""
    prepared = add_time_buckets(trades)
    observations = []

    by_side = summarize_strategy_group(prepared, strategy_name, "side_label")
    observations.extend(_best_worst_group_observations(by_side, "Side"))

    by_session = summarize_strategy_group(prepared, strategy_name, "session")
    observations.extend(_best_worst_group_observations(by_session, "Session"))

    by_year = summarize_strategy_group(prepared, strategy_name, "year")
    observations.extend(_best_worst_group_observations(by_year, "Year"))

    by_month = summarize_strategy_group(prepared, strategy_name, "month")
    losing_months = by_month[by_month["net_profit"] < 0] if not by_month.empty else pd.DataFrame()
    if not losing_months.empty:
        observations.append(f"Negative months: {len(losing_months)}")

    if not observations:
        observations.append("No clear trade-level edge detected from the available report.")

    return observations


def _summary_row(strategy_name: str, group: pd.DataFrame) -> dict:
    pnl = group["pnl"]
    stats = _pnl_stats(pnl)
    average_bars = (
        float(group["bars_in_trade"].dropna().mean())
        if "bars_in_trade" in group.columns and group["bars_in_trade"].notna().any()
        else float("nan")
    )

    return {
        "strategy_name": strategy_name,
        **stats,
        "median_trade": float(pnl.median()) if len(pnl) else 0.0,
        "best_trade": float(pnl.max()) if len(pnl) else 0.0,
        "worst_trade": float(pnl.min()) if len(pnl) else 0.0,
        "max_consecutive_losses": calculate_max_consecutive(pnl, positive=False),
        "average_bars_in_trade": average_bars,
    }


def _pnl_stats(pnl: pd.Series) -> dict:
    pnl = pd.to_numeric(pnl, errors="coerce").fillna(0.0)
    wins = int((pnl > 0).sum())
    losses = int((pnl < 0).sum())
    total_trades = int(len(pnl))
    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = float(abs(pnl[pnl < 0].sum()))

    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / total_trades * 100 if total_trades else 0.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": _profit_factor(gross_profit, gross_loss),
        "net_profit": float(pnl.sum()),
        "average_trade": float(pnl.mean()) if total_trades else 0.0,
    }


def _profit_factor(gross_profit: float, gross_loss: float) -> float:
    if gross_loss > 0:
        return gross_profit / gross_loss
    if gross_profit > 0:
        return float("inf")
    return 0.0


def _append_loss_cluster(clusters: list[dict], current: list[pd.Series], min_losses: int) -> None:
    if len(current) < min_losses:
        return

    pnl_values = [float(row["pnl"]) for row in current]
    clusters.append(
        {
            "start_time": current[0].get("entry_time"),
            "end_time": current[-1].get("entry_time"),
            "loss_count": len(current),
            "net_loss": sum(pnl_values),
            "worst_trade": min(pnl_values),
        }
    )


def _best_worst_group_observations(grouped: pd.DataFrame, label: str) -> list[str]:
    if grouped.empty:
        return []

    observations = []
    best = grouped.sort_values("net_profit", ascending=False).iloc[0]
    worst = grouped.sort_values("net_profit", ascending=True).iloc[0]
    observations.append(f"{label} best: {best['group']} net={best['net_profit']:.2f}")
    observations.append(f"{label} worst: {worst['group']} net={worst['net_profit']:.2f}")
    return observations


def _empty_loss_clusters() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "start_time",
            "end_time",
            "loss_count",
            "net_loss",
            "worst_trade",
        ]
    )


def _side_label(side: object) -> str:
    if side == "BUY":
        return "LONG"
    if side == "SELL":
        return "SHORT"
    return str(side) if side is not None else "Unknown"
