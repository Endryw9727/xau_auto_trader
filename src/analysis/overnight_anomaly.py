"""
Overnight vs intraday return anomaly (read-only research, pre-registered).

This is a single, theory-driven hypothesis rather than a broad search, so the
multiple-testing penalty stays small. The academic finding (documented for gold,
gold ETFs and equity indices) is that overnight returns (previous close -> next
open) are positive while intraday returns (open -> close) are negative.

We therefore pre-register exactly two legs per instrument:
- OVERNIGHT_LONG: hold from the previous day's close to the next day's open.
- INTRADAY_SHORT: short from the day's open to the day's close.

Each leg is evaluated on the same walk-forward + cost framework used elsewhere.
Because the directions are fixed in advance by theory, this is not a fishing
expedition. It is research only: no data fetch, no execution, no orders.
"""

from __future__ import annotations

import pandas as pd

from src.analysis.session_edge_lab import evaluate_net_returns


DAILY_COLUMNS: tuple[str, ...] = ("day", "day_open", "day_close", "overnight_return_pct", "intraday_return_pct")

OVERNIGHT_EDGE_COLUMNS: tuple[str, ...] = (
    "leg",
    "trades",
    "is_trades",
    "oos_trades",
    "mean_net_pct",
    "is_mean_pct",
    "oos_mean_pct",
    "is_t_stat",
    "oos_t_stat",
    "win_rate",
    "robust_edge",
)


def compute_overnight_intraday_returns(market_data: pd.DataFrame) -> pd.DataFrame:
    """Per calendar day: overnight (prev close -> open) and intraday (open -> close)."""
    data = _ensure_ohlc(market_data)
    if data.empty:
        return pd.DataFrame(columns=DAILY_COLUMNS)

    data = data.copy()
    data["day"] = data.index.normalize()
    rows = []
    for day, group in data.groupby("day", sort=True):
        rows.append(
            {
                "day": pd.Timestamp(day),
                "day_open": float(group["Open"].iloc[0]),
                "day_close": float(group["Close"].iloc[-1]),
            }
        )
    daily = pd.DataFrame(rows)
    if daily.empty:
        return pd.DataFrame(columns=DAILY_COLUMNS)

    daily = daily.sort_values("day").reset_index(drop=True)
    prev_close = daily["day_close"].shift(1)
    daily["overnight_return_pct"] = (daily["day_open"] - prev_close) / prev_close * 100.0
    daily["intraday_return_pct"] = (daily["day_close"] - daily["day_open"]) / daily["day_open"] * 100.0
    return daily[list(DAILY_COLUMNS)]


def evaluate_overnight_anomaly(
    market_data: pd.DataFrame,
    *,
    cost_per_trade: float = 0.0,
    min_trades: int = 40,
    oos_fraction: float = 0.3,
    t_stat_threshold: float = 1.5,
) -> pd.DataFrame:
    """Evaluate the two pre-registered legs on the walk-forward + cost framework."""
    daily = compute_overnight_intraday_returns(market_data)
    if daily.empty:
        return pd.DataFrame(columns=OVERNIGHT_EDGE_COLUMNS)

    overnight = daily["overnight_return_pct"].dropna()
    intraday = daily["intraday_return_pct"].dropna()
    cost_on = _cost_pct(cost_per_trade, daily["day_open"].to_numpy())
    cost_in = _cost_pct(cost_per_trade, daily["day_open"].to_numpy())

    overnight_net = overnight.to_numpy() - (cost_on[1:] if hasattr(cost_on, "__len__") and len(cost_on) == len(daily) else cost_on)
    intraday_net = (-intraday.to_numpy()) - cost_in

    rows = [
        {"leg": "OVERNIGHT_LONG", **evaluate_net_returns(
            overnight_net, min_trades=min_trades, oos_fraction=oos_fraction, t_stat_threshold=t_stat_threshold)},
        {"leg": "INTRADAY_SHORT", **evaluate_net_returns(
            intraday_net, min_trades=min_trades, oos_fraction=oos_fraction, t_stat_threshold=t_stat_threshold)},
    ]
    return pd.DataFrame(rows, columns=OVERNIGHT_EDGE_COLUMNS)


def _cost_pct(cost_per_trade: float, entries):
    if cost_per_trade <= 0:
        return 0.0
    series = pd.Series(entries, dtype="float64").replace(0, pd.NA)
    return (float(cost_per_trade) / series * 100.0).fillna(0.0).to_numpy()


def _ensure_ohlc(market_data: pd.DataFrame) -> pd.DataFrame:
    if market_data is None or market_data.empty:
        return pd.DataFrame()
    data = market_data.copy()
    if not isinstance(data.index, pd.DatetimeIndex):
        for column in ("Date", "time", "timestamp"):
            if column in data.columns:
                data[column] = pd.to_datetime(data[column], errors="coerce")
                data = data.dropna(subset=[column]).set_index(column)
                break
    if not isinstance(data.index, pd.DatetimeIndex):
        raise ValueError("market_data must have a DatetimeIndex or a Date/time column")
    required = {"Open", "High", "Low", "Close"}
    if not required.issubset(data.columns):
        raise ValueError(f"market_data missing OHLC columns: {sorted(required - set(data.columns))}")
    return data.sort_index()
