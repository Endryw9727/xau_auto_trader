"""
Conditional New York session edge (read-only research).

The plain "always trade the session" hypothesis found no robust edge. This module
tests a smarter, explainable idea: trade the New York session only when the
*earlier* sessions of the same day (Asia + London, which close before NY opens)
have built a given context. For each day it computes the pre-NY move and the NY
move, then evaluates two hypotheses on the same walk-forward + cost framework:

- CONTINUATION: NY continues the pre-NY direction (long after pre-up, short after
  pre-down).
- REVERSAL: NY reverses the pre-NY direction.

There is no lookahead: the conditioning feature uses only candles that close
before the NY session opens. It is research only: reads OHLCV candles, never
fetches data, never imports execution code and never sends orders.
"""

from __future__ import annotations

import pandas as pd

from src.analysis.session_edge_lab import evaluate_net_returns
from src.analysis.session_structure import classify_session


NY_DAILY_COLUMNS: tuple[str, ...] = (
    "day",
    "pre_ny_open",
    "pre_ny_close",
    "pre_ny_return_pct",
    "ny_open",
    "ny_close",
    "ny_long_return_pct",
)

NY_EDGE_COLUMNS: tuple[str, ...] = (
    "condition",
    "direction",
    "hypothesis",
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

_PRE_NY_SESSIONS = ("ASIA", "ASIA/LONDON", "LONDON")
_NY_SESSIONS = ("LONDON/US", "NEW YORK")


def build_ny_daily_frame(market_data: pd.DataFrame) -> pd.DataFrame:
    """Per day: the pre-NY move (Asia open -> London close) and the NY move."""
    data = _ensure_ohlc(market_data)
    if data.empty:
        return pd.DataFrame(columns=NY_DAILY_COLUMNS)

    data = data.copy()
    data["session"] = [classify_session(int(hour)) for hour in data.index.hour]
    data["day"] = data.index.normalize()

    rows = []
    for day, group in data.groupby("day", sort=True):
        pre = group[group["session"].isin(_PRE_NY_SESSIONS)]
        ny = group[group["session"].isin(_NY_SESSIONS)]
        if pre.empty or ny.empty:
            continue
        pre_open = float(pre["Open"].iloc[0])
        pre_close = float(pre["Close"].iloc[-1])
        ny_open = float(ny["Open"].iloc[0])
        ny_close = float(ny["Close"].iloc[-1])
        if pre_open <= 0 or ny_open <= 0:
            continue
        rows.append(
            {
                "day": pd.Timestamp(day),
                "pre_ny_open": pre_open,
                "pre_ny_close": pre_close,
                "pre_ny_return_pct": (pre_close - pre_open) / pre_open * 100.0,
                "ny_open": ny_open,
                "ny_close": ny_close,
                "ny_long_return_pct": (ny_close - ny_open) / ny_open * 100.0,
            }
        )
    return pd.DataFrame(rows, columns=NY_DAILY_COLUMNS)


def evaluate_ny_conditional_edges(
    market_data: pd.DataFrame,
    *,
    cost_per_trade: float = 0.0,
    min_trades: int = 30,
    oos_fraction: float = 0.3,
    t_stat_threshold: float = 1.5,
) -> pd.DataFrame:
    """Evaluate NY continuation/reversal edges conditioned on the pre-NY move."""
    daily = build_ny_daily_frame(market_data)
    if daily.empty:
        return pd.DataFrame(columns=NY_EDGE_COLUMNS)

    daily = daily.sort_values("day")
    cost_pct = _cost_pct(cost_per_trade, daily["ny_open"].to_numpy())
    daily = daily.assign(_cost_pct=cost_pct)

    rows = []
    for condition, mask in (
        ("PRE_UP", daily["pre_ny_return_pct"] > 0),
        ("PRE_DOWN", daily["pre_ny_return_pct"] < 0),
    ):
        subset = daily[mask]
        if subset.empty:
            continue
        long_gross = subset["ny_long_return_pct"].to_numpy()
        sub_cost = subset["_cost_pct"].to_numpy() if hasattr(subset["_cost_pct"], "to_numpy") else subset["_cost_pct"]
        for direction in ("LONG", "SHORT"):
            net = (long_gross if direction == "LONG" else -long_gross) - sub_cost
            metrics = evaluate_net_returns(
                net, min_trades=min_trades, oos_fraction=oos_fraction, t_stat_threshold=t_stat_threshold
            )
            rows.append(
                {
                    "condition": condition,
                    "direction": direction,
                    "hypothesis": _hypothesis(condition, direction),
                    **metrics,
                }
            )
    return pd.DataFrame(rows, columns=NY_EDGE_COLUMNS)


def _hypothesis(condition: str, direction: str) -> str:
    continuation = (condition == "PRE_UP" and direction == "LONG") or (
        condition == "PRE_DOWN" and direction == "SHORT"
    )
    return "CONTINUATION" if continuation else "REVERSAL"


def _cost_pct(cost_per_trade: float, entries):
    if cost_per_trade <= 0:
        return [0.0] * len(entries)
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
