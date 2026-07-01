"""
Trend-regime conditioning for the edge search (read-only research).

Companion to ``regime_conditioning`` (volatility): here the condition is the daily
*trend* at entry — is price above or below a trailing moving average. Hypothesis:
a session/direction strategy may only have an edge with the daily trend (e.g. a
LONG that works in an uptrend), which averaging over all days would hide.

The label for entering on day D uses ONLY data through day D-1 (the prior close
vs a moving average of prior closes). Any lookahead would fabricate an edge, so
it is guarded and tested. Pure research: reads OHLCV, no IO, no execution, no
orders.
"""

from __future__ import annotations

import pandas as pd

from src.analysis.session_edge_lab import _EDGE_SESSIONS, _cost_pct, _ensure_ohlc, compute_session_trades

UPTREND = "UPTREND"
DOWNTREND = "DOWNTREND"


def daily_close(market_data: pd.DataFrame) -> pd.Series:
    """Daily close series (indexed by calendar day)."""
    data = _ensure_ohlc(market_data)
    if data.empty:
        return pd.Series(dtype="float64")
    return data["Close"].groupby(data.index.normalize()).last()


def entry_trend_labels(market_data: pd.DataFrame, *, sma_lookback: int = 50) -> pd.Series:
    """Point-in-time UPTREND/DOWNTREND label per day (uses only data through D-1).

    Compares the prior day's close to a moving average of prior closes. Both are
    shifted by one day so the label for day D never sees day D's own price.
    """
    close = daily_close(market_data)
    if close.empty:
        return pd.Series(dtype="object")
    sma = close.rolling(sma_lookback, min_periods=sma_lookback).mean()
    prior_close = close.shift(1)   # entry on D knows D-1's close
    prior_sma = sma.shift(1)       # and the SMA through D-1
    labels = pd.Series(index=close.index, dtype="object")
    valid = prior_close.notna() & prior_sma.notna()
    labels[valid & (prior_close > prior_sma)] = UPTREND
    labels[valid & (prior_close <= prior_sma)] = DOWNTREND
    return labels


def trend_return_series(
    market_data: pd.DataFrame,
    symbol: str,
    *,
    cost_per_trade: float = 0.0,
    sma_lookback: int = 50,
) -> dict[str, pd.Series]:
    """Per-strategy daily net-return series split by daily trend regime.

    Keys are ``"<symbol>/<session>/<direction>/<trend>"``. Trades whose day has no
    trend label (insufficient history) are dropped.
    """
    trades = compute_session_trades(market_data)
    out: dict[str, pd.Series] = {}
    if trades.empty:
        return out
    labels = entry_trend_labels(market_data, sma_lookback=sma_lookback)
    if labels.empty:
        return out

    trades = trades.copy()
    trades["trend"] = pd.to_datetime(trades["day"]).map(labels)
    trades = trades[trades["trend"].notna()]
    if trades.empty:
        return out

    for session in _EDGE_SESSIONS:
        for trend in (UPTREND, DOWNTREND):
            subset = trades[(trades["session"] == session) & (trades["trend"] == trend)].sort_values("day")
            if subset.empty:
                continue
            entries = subset["entry"].to_numpy()
            gross_long = subset["long_return_pct"].to_numpy()
            cost_pct = _cost_pct(cost_per_trade, entries)
            index = pd.DatetimeIndex(pd.to_datetime(subset["day"]))
            for direction in ("LONG", "SHORT"):
                net = (gross_long if direction == "LONG" else -gross_long) - cost_pct
                out[f"{symbol}/{session}/{direction}/{trend}"] = pd.Series(net, index=index)
    return out
