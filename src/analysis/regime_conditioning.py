"""
Volatility-regime conditioning for the edge search (read-only research).

Hypothesis: a session/direction strategy may have no edge *on average* yet a real
edge inside a specific volatility regime (e.g. only when recent volatility is
high). This module splits each strategy's trades by a **point-in-time** volatility
regime so the conditional variants can be re-tested with the same honest machinery
(walk-forward + multiple-testing + DSR/PBO).

The regime for entering on day D uses ONLY data available through day D-1 (a
trailing ATR compared to its trailing median). Any lookahead here would fabricate
an edge, so it is guarded and tested: a volatility spike on day D can change the
label of day D+1 onward, never of day D itself.

Pure research: reads OHLCV, no IO, no execution, no orders.
"""

from __future__ import annotations

import pandas as pd

from src.analysis.session_edge_lab import _EDGE_SESSIONS, _cost_pct, _ensure_ohlc, compute_session_trades

HIGH_VOL = "HIGH_VOL"
LOW_VOL = "LOW_VOL"


def daily_true_range(market_data: pd.DataFrame) -> pd.Series:
    """Daily True Range series (indexed by calendar day)."""
    data = _ensure_ohlc(market_data)
    if data.empty:
        return pd.Series(dtype="float64")
    daily = pd.DataFrame(
        {
            "High": data["High"].groupby(data.index.normalize()).max(),
            "Low": data["Low"].groupby(data.index.normalize()).min(),
            "Close": data["Close"].groupby(data.index.normalize()).last(),
        }
    )
    prev_close = daily["Close"].shift(1)
    tr = pd.concat(
        [
            daily["High"] - daily["Low"],
            (daily["High"] - prev_close).abs(),
            (daily["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def entry_regime_labels(
    market_data: pd.DataFrame,
    *,
    atr_lookback: int = 14,
    median_window: int = 60,
    min_history: int = 30,
) -> pd.Series:
    """Point-in-time HIGH_VOL/LOW_VOL label per day (uses only data through D-1).

    ATR is a rolling mean of True Range; it is shifted by one day so the label for
    day D never sees day D's own range. The threshold is a trailing median of that
    shifted ATR. Days without enough history are left unlabelled (NaN).
    """
    tr = daily_true_range(market_data)
    if tr.empty:
        return pd.Series(dtype="object")
    atr = tr.rolling(atr_lookback, min_periods=atr_lookback).mean()
    entry_atr = atr.shift(1)  # regime for day D uses ATR through D-1
    threshold = entry_atr.rolling(median_window, min_periods=min_history).median()
    labels = pd.Series(index=tr.index, dtype="object")
    valid = entry_atr.notna() & threshold.notna()
    labels[valid & (entry_atr > threshold)] = HIGH_VOL
    labels[valid & (entry_atr <= threshold)] = LOW_VOL
    return labels


def conditional_return_series(
    market_data: pd.DataFrame,
    symbol: str,
    *,
    cost_per_trade: float = 0.0,
    atr_lookback: int = 14,
    median_window: int = 60,
) -> dict[str, pd.Series]:
    """Per-strategy daily net-return series split by volatility regime.

    Keys are ``"<symbol>/<session>/<direction>/<regime>"``. Trades whose day has
    no regime label (insufficient history) are dropped from the conditional
    variants.
    """
    trades = compute_session_trades(market_data)
    out: dict[str, pd.Series] = {}
    if trades.empty:
        return out
    labels = entry_regime_labels(
        market_data, atr_lookback=atr_lookback, median_window=median_window
    )
    if labels.empty:
        return out

    trades = trades.copy()
    trades["regime"] = pd.to_datetime(trades["day"]).map(labels)
    trades = trades[trades["regime"].notna()]
    if trades.empty:
        return out

    for session in _EDGE_SESSIONS:
        for regime in (HIGH_VOL, LOW_VOL):
            subset = trades[(trades["session"] == session) & (trades["regime"] == regime)].sort_values("day")
            if subset.empty:
                continue
            entries = subset["entry"].to_numpy()
            gross_long = subset["long_return_pct"].to_numpy()
            cost_pct = _cost_pct(cost_per_trade, entries)
            index = pd.DatetimeIndex(pd.to_datetime(subset["day"]))
            for direction in ("LONG", "SHORT"):
                net = (gross_long if direction == "LONG" else -gross_long) - cost_pct
                out[f"{symbol}/{session}/{direction}/{regime}"] = pd.Series(net, index=index)
    return out
