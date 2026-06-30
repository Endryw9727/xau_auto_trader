"""
Multi-instrument session edge lab (read-only research).

This module searches for a simple, explainable *session drift* edge on any
instrument (gold, indices like NASDAQ, FX majors): for each session
(Asia/London/New York) and each direction, it measures whether entering at the
session open and exiting at the session close has a statistically positive,
cost-adjusted expectancy that survives an out-of-sample split.

Design choices that keep it honest:
- Returns are measured in percent so different instruments are comparable.
- A round-trip cost (spread in price units) is subtracted from every trade.
- Significance uses a t-stat (mean / standard error), not win rate.
- Walk-forward: an edge must be positive AND significant in BOTH the in-sample
  and out-of-sample halves, with a minimum number of trades, to count as robust.

A symbol with no robust session edge is flagged EXCLUDE.

It is research only: it reads OHLCV candles, never fetches data, never contacts a
broker, never imports execution code and never sends orders.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from src.analysis.session_structure import classify_session


SESSION_TRADE_COLUMNS: tuple[str, ...] = (
    "day",
    "session",
    "entry",
    "exit",
    "long_return_pct",
)

EDGE_COLUMNS: tuple[str, ...] = (
    "session",
    "direction",
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

# Sessions worth testing as a drift hypothesis (skip overlaps/closed to keep the
# population clean and the windows non-overlapping).
_EDGE_SESSIONS: tuple[str, ...] = ("ASIA", "LONDON", "NEW YORK")


@dataclass(frozen=True)
class SymbolEdgeVerdict:
    """Per-symbol conclusion of the session edge search."""

    symbol: str
    verdict: str  # "KEEP" or "EXCLUDE"
    best_session: str
    best_direction: str
    best_oos_t_stat: float
    best_oos_mean_pct: float
    robust_edges: int


def compute_session_trades(market_data: pd.DataFrame) -> pd.DataFrame:
    """Build one trade per (day, session): enter at session open, exit at close."""
    data = _ensure_ohlc(market_data)
    if data.empty:
        return pd.DataFrame(columns=SESSION_TRADE_COLUMNS)

    data = data.copy()
    data["session"] = [classify_session(int(hour)) for hour in data.index.hour]
    data["day"] = data.index.normalize()
    data = data[data["session"].isin(_EDGE_SESSIONS)]
    if data.empty:
        return pd.DataFrame(columns=SESSION_TRADE_COLUMNS)

    rows = []
    for (day, session), group in data.groupby(["day", "session"], sort=True):
        entry = float(group["Open"].iloc[0])
        exit_price = float(group["Close"].iloc[-1])
        if entry <= 0:
            continue
        rows.append(
            {
                "day": pd.Timestamp(day),
                "session": session,
                "entry": entry,
                "exit": exit_price,
                "long_return_pct": (exit_price - entry) / entry * 100.0,
            }
        )
    return pd.DataFrame(rows, columns=SESSION_TRADE_COLUMNS)


def evaluate_session_edges(
    market_data: pd.DataFrame,
    *,
    cost_per_trade: float = 0.0,
    min_trades: int = 30,
    oos_fraction: float = 0.3,
    t_stat_threshold: float = 1.5,
) -> pd.DataFrame:
    """Evaluate session/direction drift edges with an out-of-sample split."""
    if not 0.0 < oos_fraction < 1.0:
        raise ValueError("oos_fraction must be between 0 and 1")
    trades = compute_session_trades(market_data)
    if trades.empty:
        return pd.DataFrame(columns=EDGE_COLUMNS)

    rows = []
    for session in _EDGE_SESSIONS:
        session_trades = trades[trades["session"] == session].sort_values("day")
        if session_trades.empty:
            continue
        entries = session_trades["entry"].to_numpy()
        gross_long = session_trades["long_return_pct"].to_numpy()
        cost_pct = _cost_pct(cost_per_trade, entries)
        for direction in ("LONG", "SHORT"):
            net = (gross_long if direction == "LONG" else -gross_long) - cost_pct
            rows.append(_edge_row(session, direction, net, min_trades, oos_fraction, t_stat_threshold))
    return pd.DataFrame(rows, columns=EDGE_COLUMNS)


def symbol_edge_verdict(symbol: str, edges: pd.DataFrame) -> SymbolEdgeVerdict:
    """Reduce an edge table to a KEEP/EXCLUDE verdict for one symbol."""
    if edges is None or edges.empty:
        return SymbolEdgeVerdict(symbol, "EXCLUDE", "", "", 0.0, 0.0, 0)

    robust = edges[edges["robust_edge"]].copy()
    if robust.empty:
        return SymbolEdgeVerdict(symbol, "EXCLUDE", "", "", 0.0, 0.0, 0)

    robust["_abs_oos_t"] = robust["oos_t_stat"].abs()
    best = robust.sort_values("_abs_oos_t", ascending=False).iloc[0]
    return SymbolEdgeVerdict(
        symbol=symbol,
        verdict="KEEP",
        best_session=str(best["session"]),
        best_direction=str(best["direction"]),
        best_oos_t_stat=float(best["oos_t_stat"]),
        best_oos_mean_pct=float(best["oos_mean_pct"]),
        robust_edges=int(len(robust)),
    )


def evaluate_net_returns(
    net,
    *,
    min_trades: int = 30,
    oos_fraction: float = 0.3,
    t_stat_threshold: float = 1.5,
) -> dict:
    """Walk-forward robustness of a net (post-cost) return series.

    Returns the metric fields shared by every edge hypothesis: in/out-of-sample
    trade counts, means, t-stats, win rate and a ``robust_edge`` flag that is
    True only when the series is significant (|t| >= threshold, same sign) in
    BOTH halves, has enough trades and a positive overall mean.
    """
    if not 0.0 < oos_fraction < 1.0:
        raise ValueError("oos_fraction must be between 0 and 1")
    series = pd.Series(net).dropna()
    n = int(len(series))
    split = max(1, int(round(n * (1.0 - oos_fraction))))
    in_sample = series.iloc[:split]
    out_sample = series.iloc[split:]

    is_t = _t_stat(in_sample)
    oos_t = _t_stat(out_sample)
    mean_net = float(series.mean()) if n else 0.0
    same_sign = (is_t >= 0) == (oos_t >= 0)
    robust = bool(
        n >= min_trades
        and len(out_sample) >= max(10, int(min_trades * oos_fraction))
        and same_sign
        and abs(is_t) >= t_stat_threshold
        and abs(oos_t) >= t_stat_threshold
        and mean_net > 0
    )
    return {
        "trades": n,
        "is_trades": int(len(in_sample)),
        "oos_trades": int(len(out_sample)),
        "mean_net_pct": round(mean_net, 6),
        "is_mean_pct": round(float(in_sample.mean()), 6) if len(in_sample) else 0.0,
        "oos_mean_pct": round(float(out_sample.mean()), 6) if len(out_sample) else 0.0,
        "is_t_stat": round(is_t, 3),
        "oos_t_stat": round(oos_t, 3),
        "win_rate": round(100.0 * float((series > 0).mean()), 2) if n else 0.0,
        "robust_edge": robust,
    }


def _edge_row(
    session: str,
    direction: str,
    net: "pd.Series | any",
    min_trades: int,
    oos_fraction: float,
    t_stat_threshold: float,
) -> dict:
    metrics = evaluate_net_returns(
        net, min_trades=min_trades, oos_fraction=oos_fraction, t_stat_threshold=t_stat_threshold
    )
    return {"session": session, "direction": direction, **metrics}


def _t_stat(series: pd.Series) -> float:
    values = pd.Series(series).dropna()
    n = len(values)
    if n < 2:
        return 0.0
    std = float(values.std(ddof=1))
    if std <= 0:
        return 0.0
    return float(values.mean()) / (std / math.sqrt(n))


def _cost_pct(cost_per_trade: float, entries) -> "any":
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
