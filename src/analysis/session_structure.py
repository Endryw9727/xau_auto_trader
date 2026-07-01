"""
Read-only market-structure analysis by trading session for XAU/USD.

This module turns local OHLCV candles into a per-day market-structure view built
around the same broker-time session model used by the V50/V51 features:

- Asia      = accumulation phase (range building / liquidity resting)
- London    = manipulation phase (sweep of Asia liquidity, false breaks)
- New York  = distribution / reversal / confirmation phase

It is diagnostics only. It reads candles, never fetches data, never contacts a
broker, never imports execution code and never sends orders. It does not change
any strategy gate, threshold or config. It exists so other read-only diagnostics
can ask: was Asia liquidity swept, on which side, was it reclaimed, and how far
is a candidate from the key Asia/prior-day levels.

The session windows mirror ``strategy_v50_pine._classify_v50_session`` so the
labels stay consistent with the ``session`` field already logged by V51.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


# Broker-time hour windows, aligned with strategy_v50_pine._classify_v50_session.
# Kept here as data so diagnostics can reason about phases without importing the
# heavy V50 feature pipeline.
def classify_session(hour: int) -> str:
    """Classify a broker-time hour into the V50/V51 session label."""
    if hour < 0 or hour > 23:
        raise ValueError("hour must be between 0 and 23")
    if hour == 23:
        return "FX CLOSED"
    if 9 <= hour < 10:
        return "ASIA/LONDON"
    if 16 <= hour < 18:
        return "LONDON/US"
    if 0 <= hour < 10:
        return "ASIA"
    if 10 <= hour < 16:
        return "LONDON"
    if 18 <= hour < 23:
        return "NEW YORK"
    return "OFF"


def session_phase(hour: int) -> str:
    """Map a broker-time hour to an accumulation/manipulation/distribution phase."""
    session = classify_session(hour)
    if session in {"FX CLOSED", "OFF"}:
        return "CLOSED"
    if session == "ASIA":
        return "ACCUMULATION"
    if session in {"ASIA/LONDON", "LONDON"}:
        return "MANIPULATION"
    return "DISTRIBUTION"  # LONDON/US, NEW YORK


DAILY_STRUCTURE_COLUMNS: tuple[str, ...] = (
    "day",
    "asia_high",
    "asia_low",
    "asia_candles",
    "london_high",
    "london_low",
    "london_candles",
    "swept_asia_high",
    "swept_asia_low",
    "sweep_side",
    "reclaimed_range",
    "manipulation_label",
    "ny_open",
    "ny_close",
    "ny_direction",
)


@dataclass(frozen=True)
class LevelDistance:
    """Nearest key level to a price and the signed/absolute distance to it."""

    nearest_level_name: str
    nearest_level_price: float | None
    distance: float | None
    in_asia_range: bool


def add_session_columns(market_data: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with ``session`` and ``phase`` columns from the index hour."""
    data = _ensure_datetime_index(market_data)
    if data.empty:
        result = data.copy()
        result["session"] = pd.Series(dtype=str)
        result["phase"] = pd.Series(dtype=str)
        return result
    hours = data.index.hour
    result = data.copy()
    result["session"] = [classify_session(int(hour)) for hour in hours]
    result["phase"] = [session_phase(int(hour)) for hour in hours]
    return result


def build_daily_structure(market_data: pd.DataFrame) -> pd.DataFrame:
    """Build a per-day market-structure summary from OHLCV candles."""
    data = add_session_columns(market_data)
    if data.empty:
        return pd.DataFrame(columns=DAILY_STRUCTURE_COLUMNS)

    required = {"High", "Low", "Open", "Close"}
    if not required.issubset(data.columns):
        raise ValueError(f"market_data missing OHLC columns: {sorted(required - set(data.columns))}")

    data = data.copy()
    data["day"] = data.index.normalize()
    rows = [_day_structure(day, group) for day, group in data.groupby("day")]
    return pd.DataFrame(rows, columns=DAILY_STRUCTURE_COLUMNS)


def distance_from_levels(price: float, structure_row: pd.Series | dict) -> LevelDistance:
    """Return the nearest Asia/prior-day key level to ``price`` and the distance."""
    candidates: list[tuple[str, float]] = []
    for name in ("asia_high", "asia_low", "london_high", "london_low"):
        value = _float_or_none(structure_row.get(name) if hasattr(structure_row, "get") else None)
        if value is not None:
            candidates.append((name, value))

    asia_high = _float_or_none(structure_row.get("asia_high"))
    asia_low = _float_or_none(structure_row.get("asia_low"))
    in_range = bool(asia_high is not None and asia_low is not None and asia_low <= price <= asia_high)

    if not candidates:
        return LevelDistance("none", None, None, in_range)

    nearest_name, nearest_price = min(candidates, key=lambda item: abs(price - item[1]))
    return LevelDistance(nearest_name, nearest_price, abs(price - nearest_price), in_range)


def _day_structure(day: pd.Timestamp, group: pd.DataFrame) -> dict:
    asia = group[group["session"] == "ASIA"]
    london = group[group["session"].isin(["ASIA/LONDON", "LONDON"])]
    ny = group[group["session"].isin(["LONDON/US", "NEW YORK"])]

    asia_high = float(asia["High"].max()) if not asia.empty else None
    asia_low = float(asia["Low"].min()) if not asia.empty else None
    london_high = float(london["High"].max()) if not london.empty else None
    london_low = float(london["Low"].min()) if not london.empty else None

    swept_high = bool(asia_high is not None and london_high is not None and london_high > asia_high)
    swept_low = bool(asia_low is not None and london_low is not None and london_low < asia_low)
    sweep_side = _sweep_side(swept_high, swept_low)
    reclaimed = _reclaimed_range(london, asia_high, asia_low, swept_high, swept_low)
    manipulation = _manipulation_label(sweep_side, reclaimed)

    ny_open = float(ny["Open"].iloc[0]) if not ny.empty else None
    ny_close = float(ny["Close"].iloc[-1]) if not ny.empty else None
    ny_direction = _direction(ny_open, ny_close)

    return {
        "day": pd.Timestamp(day),
        "asia_high": asia_high,
        "asia_low": asia_low,
        "asia_candles": int(len(asia)),
        "london_high": london_high,
        "london_low": london_low,
        "london_candles": int(len(london)),
        "swept_asia_high": swept_high,
        "swept_asia_low": swept_low,
        "sweep_side": sweep_side,
        "reclaimed_range": reclaimed,
        "manipulation_label": manipulation,
        "ny_open": ny_open,
        "ny_close": ny_close,
        "ny_direction": ny_direction,
    }


def _sweep_side(swept_high: bool, swept_low: bool) -> str:
    if swept_high and swept_low:
        return "BOTH"
    if swept_high:
        return "BUY_SIDE"  # Asia high (buy-side liquidity) was taken
    if swept_low:
        return "SELL_SIDE"  # Asia low (sell-side liquidity) was taken
    return "NONE"


def _reclaimed_range(
    london: pd.DataFrame,
    asia_high: float | None,
    asia_low: float | None,
    swept_high: bool,
    swept_low: bool,
) -> bool:
    """True if, on/after the candle that swept, a London candle closes back inside.

    Only closes from the sweep candle onward count: a candle that closed inside
    the range BEFORE the sweep must not be mistaken for a reclaim of that sweep.
    """
    if asia_high is None or asia_low is None or london.empty or not (swept_high or swept_low):
        return False
    highs = london["High"].to_numpy()
    lows = london["Low"].to_numpy()
    closes = london["Close"].to_numpy()
    if swept_high:
        sweep_idx = next((i for i, high in enumerate(highs) if high > asia_high), None)
        if sweep_idx is not None and any(closes[j] < asia_high for j in range(sweep_idx, len(closes))):
            return True
    if swept_low:
        sweep_idx = next((i for i, low in enumerate(lows) if low < asia_low), None)
        if sweep_idx is not None and any(closes[j] > asia_low for j in range(sweep_idx, len(closes))):
            return True
    return False


def _manipulation_label(sweep_side: str, reclaimed: bool) -> str:
    if sweep_side == "NONE":
        return "no_sweep"
    if not reclaimed:
        return "sweep_not_reclaimed"
    if sweep_side == "SELL_SIDE":
        return "london_sweep_low_reclaimed"  # bullish manipulation (V long context)
    if sweep_side == "BUY_SIDE":
        return "london_sweep_high_reclaimed"  # bearish manipulation (V short context)
    return "london_sweep_both_reclaimed"


def _direction(open_price: float | None, close_price: float | None) -> str:
    if open_price is None or close_price is None:
        return "UNKNOWN"  # no candles for the session yet (e.g. NY not open)
    if close_price > open_price:
        return "UP"
    if close_price < open_price:
        return "DOWN"
    return "FLAT"


def _ensure_datetime_index(market_data: pd.DataFrame) -> pd.DataFrame:
    if market_data is None or market_data.empty:
        return pd.DataFrame()
    data = market_data.copy()
    if isinstance(data.index, pd.DatetimeIndex):
        return data.sort_index()
    for column in ("Date", "time", "timestamp"):
        if column in data.columns:
            data[column] = pd.to_datetime(data[column], errors="coerce")
            data = data.dropna(subset=[column]).set_index(column)
            return data.sort_index()
    raise ValueError("market_data must have a DatetimeIndex or a Date/time column")


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    return float(value)
