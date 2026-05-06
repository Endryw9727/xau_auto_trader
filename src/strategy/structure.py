"""
Market structure utilities.

This module identifies basic price structure:
- swing highs
- swing lows
- higher highs / higher lows
- lower highs / lower lows
- bullish, bearish, or ranging market state
- break of structure
- change of character

The first version is intentionally simple and testable.
It will be improved later with stronger trading logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


TrendState = Literal["BULLISH", "BEARISH", "RANGE", "UNKNOWN"]
StructureEvent = Literal["BOS_BULLISH", "BOS_BEARISH", "CHOCH_BULLISH", "CHOCH_BEARISH", "NONE"]


@dataclass(frozen=True)
class MarketStructureSummary:
    """Summary of the latest market structure state."""

    trend: TrendState
    last_swing_high: float | None
    last_swing_low: float | None
    previous_swing_high: float | None
    previous_swing_low: float | None
    event: StructureEvent


def add_swing_points(df: pd.DataFrame, lookback: int = 2) -> pd.DataFrame:
    """
    Add swing high and swing low columns.

    A swing high is a candle whose High is greater than nearby highs.
    A swing low is a candle whose Low is lower than nearby lows.
    """
    _validate_ohlc(df)
    _validate_lookback(lookback)

    result = df.copy()
    result["SWING_HIGH"] = False
    result["SWING_LOW"] = False

    for i in range(lookback, len(result) - lookback):
        current_high = result["High"].iloc[i]
        current_low = result["Low"].iloc[i]

        left_highs = result["High"].iloc[i - lookback : i]
        right_highs = result["High"].iloc[i + 1 : i + 1 + lookback]

        left_lows = result["Low"].iloc[i - lookback : i]
        right_lows = result["Low"].iloc[i + 1 : i + 1 + lookback]

        if current_high > left_highs.max() and current_high > right_highs.max():
            result.iloc[i, result.columns.get_loc("SWING_HIGH")] = True

        if current_low < left_lows.min() and current_low < right_lows.min():
            result.iloc[i, result.columns.get_loc("SWING_LOW")] = True

    return result


def get_latest_swing_highs(df: pd.DataFrame, count: int = 2) -> list[float]:
    """Return the latest swing high values."""
    _validate_swing_columns(df)

    swing_highs = df.loc[df["SWING_HIGH"], "High"].tail(count).tolist()
    return [float(value) for value in swing_highs]


def get_latest_swing_lows(df: pd.DataFrame, count: int = 2) -> list[float]:
    """Return the latest swing low values."""
    _validate_swing_columns(df)

    swing_lows = df.loc[df["SWING_LOW"], "Low"].tail(count).tolist()
    return [float(value) for value in swing_lows]


def detect_trend_from_swings(df: pd.DataFrame) -> TrendState:
    """
    Detect simple market trend using the latest two swing highs and lows.

    Bullish:
    - latest swing high > previous swing high
    - latest swing low > previous swing low

    Bearish:
    - latest swing high < previous swing high
    - latest swing low < previous swing low
    """
    highs = get_latest_swing_highs(df, count=2)
    lows = get_latest_swing_lows(df, count=2)

    if len(highs) < 2 or len(lows) < 2:
        return "UNKNOWN"

    previous_high, latest_high = highs[0], highs[1]
    previous_low, latest_low = lows[0], lows[1]

    if latest_high > previous_high and latest_low > previous_low:
        return "BULLISH"

    if latest_high < previous_high and latest_low < previous_low:
        return "BEARISH"

    return "RANGE"


def detect_break_of_structure(df: pd.DataFrame, previous_trend: TrendState = "UNKNOWN") -> StructureEvent:
    """
    Detect a basic break of structure or change of character.

    If price closes above the latest swing high:
    - BOS_BULLISH if previous trend was bullish/unknown/range
    - CHOCH_BULLISH if previous trend was bearish

    If price closes below the latest swing low:
    - BOS_BEARISH if previous trend was bearish/unknown/range
    - CHOCH_BEARISH if previous trend was bullish
    """
    _validate_swing_columns(df)

    if df.empty:
        return "NONE"

    highs = get_latest_swing_highs(df, count=1)
    lows = get_latest_swing_lows(df, count=1)

    if not highs or not lows:
        return "NONE"

    last_close = float(df["Close"].iloc[-1])
    last_swing_high = highs[-1]
    last_swing_low = lows[-1]

    if last_close > last_swing_high:
        if previous_trend == "BEARISH":
            return "CHOCH_BULLISH"
        return "BOS_BULLISH"

    if last_close < last_swing_low:
        if previous_trend == "BULLISH":
            return "CHOCH_BEARISH"
        return "BOS_BEARISH"

    return "NONE"


def summarize_market_structure(df: pd.DataFrame, lookback: int = 2) -> MarketStructureSummary:
    """
    Return a summary of the current market structure.
    """
    structured = add_swing_points(df, lookback=lookback)

    highs = get_latest_swing_highs(structured, count=2)
    lows = get_latest_swing_lows(structured, count=2)

    trend = detect_trend_from_swings(structured)
    event = detect_break_of_structure(structured, previous_trend=trend)

    previous_high = highs[0] if len(highs) == 2 else None
    latest_high = highs[-1] if highs else None

    previous_low = lows[0] if len(lows) == 2 else None
    latest_low = lows[-1] if lows else None

    return MarketStructureSummary(
        trend=trend,
        last_swing_high=latest_high,
        last_swing_low=latest_low,
        previous_swing_high=previous_high,
        previous_swing_low=previous_low,
        event=event,
    )


def _validate_ohlc(df: pd.DataFrame) -> None:
    """Validate OHLC columns."""
    required = ["Open", "High", "Low", "Close"]
    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"Missing required OHLC columns: {missing}")


def _validate_swing_columns(df: pd.DataFrame) -> None:
    """Validate swing columns."""
    _validate_ohlc(df)

    required = ["SWING_HIGH", "SWING_LOW"]
    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"Missing required swing columns: {missing}")


def _validate_lookback(lookback: int) -> None:
    """Validate swing lookback."""
    if lookback <= 0:
        raise ValueError("lookback must be greater than 0")
