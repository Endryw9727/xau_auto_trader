"""
Daily coverage diagnostics for final V50 strategy candidates.

The helpers operate on simulated backtest trades and local OHLCV data only.
They do not execute trades or connect to brokers.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.analysis.trade_level_diagnostics import prepare_trade_report
from src.backtesting.metrics import calculate_max_consecutive
from src.strategy_lab.strategy_v50_candidates import FINAL_CANDIDATE_STRATEGY_NAMES


DEFAULT_DAILY_COVERAGE_PATH = Path("reports/strategy_lab/v50_daily_coverage.csv")
DEFAULT_DAILY_BREAKDOWN_PATH = Path("reports/strategy_lab/v50_daily_breakdown.csv")
TRADES_BY_STRATEGY_PATH = Path("reports/backtests/trades_by_strategy.csv")
TRADES_PATH = Path("reports/backtests/trades.csv")

DAILY_COVERAGE_COLUMNS = [
    "strategy_name",
    "total_trading_days",
    "active_trading_days",
    "no_trade_days",
    "active_day_ratio",
    "total_trades",
    "trades_per_active_day",
    "trades_per_calendar_day",
    "average_trades_per_day",
    "median_trades_per_day",
    "max_trades_per_day",
    "daily_profit_factor",
    "daily_win_rate",
    "positive_days",
    "negative_days",
    "flat_days",
]
DAILY_BREAKDOWN_COLUMNS = [
    "strategy_name",
    "trade_date",
    "trade_count",
    "wins",
    "losses",
    "net_profit",
    "gross_profit",
    "gross_loss",
    "daily_profit_factor",
    "max_consecutive_losses",
    "has_trade",
    "volatility_sufficient",
    "daily_range",
]


def load_strategy_trade_report(
    paths: tuple[Path, ...] = (TRADES_BY_STRATEGY_PATH, TRADES_PATH),
) -> pd.DataFrame | None:
    """Load the first available strategy-tagged trade report."""
    for path in paths:
        if not path.exists():
            continue
        trades = pd.read_csv(path)
        if "strategy_name" in trades.columns and ("pnl" in trades.columns or "profit_loss" in trades.columns):
            return trades
    return None


def build_daily_breakdown(
    trades: pd.DataFrame,
    strategy_names: tuple[str, ...] = FINAL_CANDIDATE_STRATEGY_NAMES,
    market_data: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return one row per strategy/day with trade and volatility coverage."""
    prepared = _prepare_trades(trades, strategy_names)
    calendar = _trading_calendar(prepared, market_data)
    volatility = _daily_volatility(market_data)
    rows = []

    for strategy_name in strategy_names:
        strategy_trades = prepared[prepared["strategy_name"] == strategy_name].copy()
        grouped = dict(tuple(strategy_trades.groupby("trade_date", dropna=False)))

        for trade_date in calendar:
            day_trades = grouped.get(trade_date, pd.DataFrame())
            rows.append(_daily_row(strategy_name, trade_date, day_trades, volatility))

    return pd.DataFrame(rows, columns=DAILY_BREAKDOWN_COLUMNS)


def build_daily_coverage_report(daily_breakdown: pd.DataFrame) -> pd.DataFrame:
    """Summarize daily coverage rows by strategy."""
    if daily_breakdown.empty:
        return pd.DataFrame(columns=DAILY_COVERAGE_COLUMNS)

    rows = []
    for strategy_name, group in daily_breakdown.groupby("strategy_name", sort=False):
        trade_counts = pd.to_numeric(group["trade_count"], errors="coerce").fillna(0)
        daily_pnl = pd.to_numeric(group["net_profit"], errors="coerce").fillna(0.0)
        total_days = int(len(group))
        active_days = int((trade_counts > 0).sum())
        positive_days = int((daily_pnl > 0).sum())
        negative_days = int((daily_pnl < 0).sum())
        flat_days = int((daily_pnl == 0).sum())
        gross_profit = float(daily_pnl[daily_pnl > 0].sum())
        gross_loss = float(abs(daily_pnl[daily_pnl < 0].sum()))

        rows.append(
            {
                "strategy_name": strategy_name,
                "total_trading_days": total_days,
                "active_trading_days": active_days,
                "no_trade_days": total_days - active_days,
                "active_day_ratio": active_days / total_days if total_days else 0.0,
                "total_trades": int(trade_counts.sum()),
                "trades_per_active_day": float(trade_counts.sum() / active_days) if active_days else 0.0,
                "trades_per_calendar_day": float(trade_counts.sum() / total_days) if total_days else 0.0,
                "average_trades_per_day": float(trade_counts.mean()) if total_days else 0.0,
                "median_trades_per_day": float(trade_counts.median()) if total_days else 0.0,
                "max_trades_per_day": int(trade_counts.max()) if total_days else 0,
                "daily_profit_factor": _profit_factor(gross_profit, gross_loss),
                "daily_win_rate": positive_days / active_days * 100 if active_days else 0.0,
                "positive_days": positive_days,
                "negative_days": negative_days,
                "flat_days": flat_days,
            }
        )

    return pd.DataFrame(rows, columns=DAILY_COVERAGE_COLUMNS)


def export_daily_coverage_reports(
    coverage: pd.DataFrame,
    breakdown: pd.DataFrame,
    coverage_path: str | Path = DEFAULT_DAILY_COVERAGE_PATH,
    breakdown_path: str | Path = DEFAULT_DAILY_BREAKDOWN_PATH,
) -> tuple[Path, Path]:
    """Export daily coverage summary and day-level rows."""
    coverage_path = Path(coverage_path)
    breakdown_path = Path(breakdown_path)
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    breakdown_path.parent.mkdir(parents=True, exist_ok=True)
    coverage.to_csv(coverage_path, index=False)
    breakdown.to_csv(breakdown_path, index=False)
    return coverage_path, breakdown_path


def worst_days(daily_breakdown: pd.DataFrame, strategy_name: str, limit: int = 10) -> pd.DataFrame:
    """Return the worst daily P&L rows for one strategy."""
    return _select_days(daily_breakdown, strategy_name, ascending=True, limit=limit)


def best_days(daily_breakdown: pd.DataFrame, strategy_name: str, limit: int = 10) -> pd.DataFrame:
    """Return the best daily P&L rows for one strategy."""
    return _select_days(daily_breakdown, strategy_name, ascending=False, limit=limit)


def loss_cluster_days(
    daily_breakdown: pd.DataFrame,
    strategy_name: str,
    min_consecutive_losses: int = 2,
) -> pd.DataFrame:
    """Return days that contain an intra-day consecutive loss cluster."""
    if daily_breakdown.empty:
        return pd.DataFrame(columns=DAILY_BREAKDOWN_COLUMNS)

    rows = daily_breakdown[
        (daily_breakdown["strategy_name"] == strategy_name)
        & (pd.to_numeric(daily_breakdown["max_consecutive_losses"], errors="coerce").fillna(0) >= min_consecutive_losses)
    ].copy()
    return rows.sort_values(["max_consecutive_losses", "net_profit"], ascending=[False, True]).reset_index(drop=True)


def no_trade_volatile_days(daily_breakdown: pd.DataFrame, strategy_name: str, limit: int = 20) -> pd.DataFrame:
    """Return no-trade days with sufficient daily range when market data is available."""
    if daily_breakdown.empty or "volatility_sufficient" not in daily_breakdown.columns:
        return pd.DataFrame(columns=DAILY_BREAKDOWN_COLUMNS)

    rows = daily_breakdown[
        (daily_breakdown["strategy_name"] == strategy_name)
        & (~daily_breakdown["has_trade"].astype(bool))
        & (daily_breakdown["volatility_sufficient"].astype(bool))
    ].copy()
    return rows.sort_values("daily_range", ascending=False).head(limit).reset_index(drop=True)


def _prepare_trades(trades: pd.DataFrame, strategy_names: tuple[str, ...]) -> pd.DataFrame:
    prepared = prepare_trade_report(trades)
    if prepared.empty or "strategy_name" not in prepared.columns:
        return pd.DataFrame(columns=list(prepared.columns) + ["trade_date"])

    prepared = prepared[prepared["strategy_name"].isin(strategy_names)].copy()
    if "entry_time" not in prepared.columns:
        prepared["entry_time"] = pd.NaT
    prepared["entry_time"] = pd.to_datetime(prepared["entry_time"], errors="coerce")
    prepared = prepared.dropna(subset=["entry_time"]).sort_values("entry_time").reset_index(drop=True)
    prepared["trade_date"] = prepared["entry_time"].dt.date.astype("string")
    return prepared


def _trading_calendar(prepared: pd.DataFrame, market_data: pd.DataFrame | None) -> list[str]:
    if market_data is not None and not market_data.empty:
        market_index = _market_datetime_index(market_data)
        if market_index is not None and len(market_index):
            return sorted(pd.Series(market_index.date).astype("string").unique().tolist())

    if prepared.empty or "trade_date" not in prepared.columns:
        return []

    return sorted(prepared["trade_date"].dropna().astype("string").unique().tolist())


def _daily_volatility(market_data: pd.DataFrame | None) -> dict[str, dict]:
    if market_data is None or market_data.empty:
        return {}

    market_index = _market_datetime_index(market_data)
    if market_index is None:
        return {}

    data = market_data.copy()
    data.index = market_index
    column_map = {column.lower(): column for column in data.columns}
    high_column = column_map.get("high")
    low_column = column_map.get("low")
    if high_column is None or low_column is None:
        return {}

    daily = data.groupby(data.index.date).agg({high_column: "max", low_column: "min"})
    daily["daily_range"] = daily[high_column] - daily[low_column]
    threshold = float(daily["daily_range"].median()) if not daily.empty else 0.0

    return {
        str(date): {
            "daily_range": float(row["daily_range"]),
            "volatility_sufficient": bool(row["daily_range"] >= threshold),
        }
        for date, row in daily.iterrows()
    }


def _daily_row(
    strategy_name: str,
    trade_date: str,
    day_trades: pd.DataFrame,
    volatility: dict[str, dict],
) -> dict:
    pnl = pd.to_numeric(day_trades.get("pnl", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    wins = int((pnl > 0).sum())
    losses = int((pnl < 0).sum())
    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = float(abs(pnl[pnl < 0].sum()))
    volatility_row = volatility.get(str(trade_date), {})

    return {
        "strategy_name": strategy_name,
        "trade_date": trade_date,
        "trade_count": int(len(day_trades)),
        "wins": wins,
        "losses": losses,
        "net_profit": float(pnl.sum()),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "daily_profit_factor": _profit_factor(gross_profit, gross_loss),
        "max_consecutive_losses": calculate_max_consecutive(pnl, positive=False) if len(pnl) else 0,
        "has_trade": bool(len(day_trades)),
        "volatility_sufficient": bool(volatility_row.get("volatility_sufficient", False)),
        "daily_range": float(volatility_row.get("daily_range", 0.0)),
    }


def _market_datetime_index(market_data: pd.DataFrame) -> pd.DatetimeIndex | None:
    if isinstance(market_data.index, pd.DatetimeIndex):
        return market_data.index
    if "Date" in market_data.columns:
        return pd.DatetimeIndex(pd.to_datetime(market_data["Date"], errors="coerce").dropna())
    if "time" in market_data.columns:
        return pd.DatetimeIndex(pd.to_datetime(market_data["time"], errors="coerce").dropna())
    return None


def _profit_factor(gross_profit: float, gross_loss: float) -> float:
    if gross_loss > 0:
        return gross_profit / gross_loss
    if gross_profit > 0:
        return float("inf")
    return 0.0


def _select_days(
    daily_breakdown: pd.DataFrame,
    strategy_name: str,
    *,
    ascending: bool,
    limit: int,
) -> pd.DataFrame:
    if daily_breakdown.empty:
        return pd.DataFrame(columns=DAILY_BREAKDOWN_COLUMNS)

    rows = daily_breakdown[
        (daily_breakdown["strategy_name"] == strategy_name)
        & (daily_breakdown["trade_count"] > 0)
    ].copy()
    return rows.sort_values("net_profit", ascending=ascending).head(limit).reset_index(drop=True)
