"""
Designed stop/target trade simulation (read-only research).

The session edge lab measures the *raw* open->close drift. Real trading uses a
designed stop-loss and take-profit, i.e. a chosen reward:risk. This module turns a
session entry into such a trade: enter at the session open, place a stop and a
target, and simulate the first-touch outcome over the following candles.

Honest conventions (match ``v51_outcome_simulation``):
- First touch wins; if a single candle's range spans BOTH stop and target we
  cannot know the order from OHLC, so we assume the STOP first (worst case).
- No lookahead: only candles at/after entry are inspected, in order.
- If neither barrier is hit within the window, the trade is marked to market at
  the last close (TIMEOUT) in R units.

Outputs are per-trade R-multiples (a loss = -1R), ready for the expectancy /
Monte Carlo / DSR-PBO machinery. Pure research: no IO, no execution, no orders.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.analysis.session_edge_lab import _EDGE_SESSIONS, _ensure_ohlc
from src.analysis.session_structure import classify_session


@dataclass(frozen=True)
class BarrierOutcome:
    outcome: str          # "WIN" | "LOSS" | "TIMEOUT"
    r_multiple: float     # profit in R (loss = -1.0)
    bars_held: int


def simulate_barrier(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    *,
    entry_price: float,
    stop_price: float,
    target_price: float,
    side: str,
) -> BarrierOutcome:
    """First-touch stop/target outcome over a window of candles (stop-first on ties)."""
    risk = abs(entry_price - stop_price)
    n = len(highs)
    if risk <= 0 or n == 0:
        return BarrierOutcome("TIMEOUT", 0.0, 0)
    reward_r = abs(target_price - entry_price) / risk
    long = side == "LONG"
    for i in range(n):
        hi = float(highs[i])
        lo = float(lows[i])
        hit_stop = lo <= stop_price if long else hi >= stop_price
        hit_target = hi >= target_price if long else lo <= target_price
        if hit_stop:  # worst case first
            return BarrierOutcome("LOSS", -1.0, i + 1)
        if hit_target:
            return BarrierOutcome("WIN", round(reward_r, 4), i + 1)
    last_close = float(closes[-1])
    mark = (last_close - entry_price) / risk if long else (entry_price - last_close) / risk
    return BarrierOutcome("TIMEOUT", round(mark, 4), n)


def session_designed_trades(
    market_data: pd.DataFrame,
    symbol: str,
    *,
    sl_pct: float = 0.3,
    reward_risk: float = 2.0,
    cost_r: float = 0.0,
) -> dict[str, pd.Series]:
    """Designed-R:R trade series per ``<symbol>/<session>/<direction>``.

    For each (day, session): enter at the session's first candle open, place the
    stop ``sl_pct`` percent away and the target ``reward_risk`` times as far, and
    simulate first-touch over that session's candles. Returns per-trade R-multiples
    (net of ``cost_r`` R of costs), indexed by day.
    """
    if sl_pct <= 0 or reward_risk <= 0:
        raise ValueError("sl_pct and reward_risk must be positive")
    data = _ensure_ohlc(market_data)
    if data.empty:
        return {}
    data = data.copy()
    data["session"] = [classify_session(int(hour)) for hour in data.index.hour]
    data["day"] = data.index.normalize()
    data = data[data["session"].isin(_EDGE_SESSIONS)]
    if data.empty:
        return {}

    results: dict[str, list[tuple[pd.Timestamp, float]]] = {}
    for (day, session), group in data.groupby(["day", "session"], sort=True):
        group = group.sort_index()
        entry = float(group["Open"].iloc[0])
        if entry <= 0:
            continue
        highs = group["High"].to_numpy()
        lows = group["Low"].to_numpy()
        closes = group["Close"].to_numpy()
        for direction in ("LONG", "SHORT"):
            if direction == "LONG":
                stop = entry * (1.0 - sl_pct / 100.0)
                target = entry * (1.0 + sl_pct * reward_risk / 100.0)
            else:
                stop = entry * (1.0 + sl_pct / 100.0)
                target = entry * (1.0 - sl_pct * reward_risk / 100.0)
            outcome = simulate_barrier(
                highs, lows, closes,
                entry_price=entry, stop_price=stop, target_price=target, side=direction,
            )
            key = f"{symbol}/{session}/{direction}"
            results.setdefault(key, []).append((pd.Timestamp(day), outcome.r_multiple - cost_r))

    return {
        key: pd.Series([r for _, r in rows], index=pd.DatetimeIndex([d for d, _ in rows]))
        for key, rows in results.items()
    }
