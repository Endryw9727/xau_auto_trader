"""
Market structure analysis for XAU/USD.

This module identifies:
- swing highs and swing lows
- trend direction
- break of structure (BOS)
- change of character (CHOCH)

These concepts help understand the current market phase.
They are not signals by themselves.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

TrendDirection = Literal["UP", "DOWN", "NEUTRAL"]

def detect_swing_highs(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    Detect swing highs.

    A swing high is a candle whose high is higher than the highs
    of the surrounding `window` candles on both sides.
    """
    if "High" not in df.columns:
        raise ValueError("DataFrame must contain a 'High' column")

    result = df.copy()
    result["swing_high"] = False

    for i in range(window, len(result) - window):
        current_high = result["High"].iloc[i]
        left_highs = result["High"].iloc[i - window:i]
        right_highs = result["High"].iloc[i + 1:i + window + 1]

        if current_high > left_highs.max() and current_high > right_highs.max():
            result.at[result.index[i], "swing_high"] = True

    return result

def detect_swing_lows(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    Detect swing lows.

    A swing low is a candle whose low is lower than the lows
    of the surrounding `window` candles on both sides.
    """
    if "Low" not in df.columns:
        raise ValueError("DataFrame must contain a 'Low' column")

    result = df.copy()
    result["swing_low"] = False

    for i in range(window, len(result) - window):
        current_low = result["Low"].iloc[i]
        left_lows = result["Low"].iloc[i - window:i]
        right_lows = result["Low"].iloc[i + 1:i + window + 1]

        if current_low < left_lows.min() and current_low < right_lows.min():
            result.at[result.index[i], "swing_low"] = True

    return result

def detect_trend(df: pd.DataFrame, lookback: int = 50) -> TrendDirection:
    """
    Detect the current trend based on swing highs and lows.

    UP trend:
    - recent swing highs are higher than previous swing highs
    - recent swing lows are higher than previous swing lows

    DOWN trend:
    - recent swing highs are lower than previous swing highs
    - recent swing lows are lower than previous swing lows
    """
    if len(df) < lookback * 2:
        return "NEUTRAL"

    recent = df.iloc[-lookback:]
    previous = df.iloc[-lookback * 2:-lookback]

    recent_highs = recent["High"].max()
    previous_highs = previous["High"].max()
    recent_lows = recent["Low"].min()
    previous_lows = previous["Low"].min()

    if recent_highs > previous_highs and recent_lows > previous_lows:
        return "UP"

    if recent_highs < previous_highs and recent_lows < previous_lows:
        return "DOWN"

    return "NEUTRAL"

def detect_bos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect Break of Structure (BOS).

    A bullish BOS happens when price breaks above a recent swing high.
    A bearish BOS happens when price breaks below a recent swing low.
    """
    if "High" not in df.columns or "Low" not in df.columns:
        raise ValueError("DataFrame must contain 'High' and 'Low' columns")

    result = detect_swing_highs(df)
    result = detect_swing_lows(result)

    result["BOS_bullish"] = False
    result["BOS_bearish"] = False

    swing_high_indices = result.index[result["swing_high"]].tolist()
    swing_low_indices = result.index[result["swing_low"]].tolist()

    for i in range(1, len(result)):
        current_high = result["High"].iloc[i]
        current_low = result["Low"].iloc[i]

        previous_swing_highs = [
            result.loc[idx, "High"]
            for idx in swing_high_indices
            if idx < result.index[i]
        ]

        previous_swing_lows = [
            result.loc[idx, "Low"]
            for idx in swing_low_indices
            if idx < result.index[i]
        ]

        if previous_swing_highs and current_high > max(previous_swing_highs):
            result.at[result.index[i], "BOS_bullish"] = True

        if previous_swing_lows and current_low < min(previous_swing_lows):
            result.at[result.index[i], "BOS_bearish"] = True

    return result

def detect_choch(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect Change of Character (CHOCH).

    A bullish CHOCH happens when price makes a higher low after a downtrend.
    A bearish CHOCH happens when price makes a lower high after an uptrend.
    """
    result = detect_bos(df.copy())
    result["CHOCH_bullish"] = False
    result["CHOCH_bearish"] = False

    swing_low_indices = result.index[result["swing_low"]].tolist()
    swing_high_indices = result.index[result["swing_high"]].tolist()

    for i in range(2, len(swing_low_indices)):
        current_low = result.loc[swing_low_indices[i], "Low"]
        previous_low = result.loc[swing_low_indices[i - 1], "Low"]
        previous_previous_low = result.loc[swing_low_indices[i - 2], "Low"]

        if previous_low < previous_previous_low and current_low > previous_low:
            result.at[swing_low_indices[i], "CHOCH_bullish"] = True

    for i in range(2, len(swing_high_indices)):
        current_high = result.loc[swing_high_indices[i], "High"]
        previous_high = result.loc[swing_high_indices[i - 1], "High"]
        previous_previous_high = result.loc[swing_high_indices[i - 2], "High"]

        if previous_high > previous_previous_high and current_high < previous_high:
            result.at[swing_high_indices[i], "CHOCH_bearish"] = True

    return result

def analyze_structure(df: pd.DataFrame) -> dict:
    """
    Analyze market structure and return a summary dictionary.
    """
    if df.empty:
        return {
            "trend": "NEUTRAL",
            "last_swing_high": None,
            "last_swing_low": None,
            "last_bos": None,
            "last_choch": None,
        }

    result = detect_choch(df)

    trend = detect_trend(result)

    swing_highs = result[result["swing_high"]]
    swing_lows = result[result["swing_low"]]
    bos_bullish = result[result["BOS_bullish"]]
    bos_bearish = result[result["BOS_bearish"]]
    choch_bullish = result[result["CHOCH_bullish"]]
    choch_bearish = result[result["CHOCH_bearish"]]

    last_swing_high = float(swing_highs["High"].iloc[-1]) if not swing_highs.empty else None
    last_swing_low = float(swing_lows["Low"].iloc[-1]) if not swing_lows.empty else None

    last_bos = None
    if not bos_bullish.empty:
        last_bos = "bullish"
    elif not bos_bearish.empty:
        last_bos = "bearish"

    last_choch = None
    if not choch_bullish.empty:
        last_choch = "bullish"
    elif not choch_bearish.empty:
        last_choch = "bearish"

    return {
        "trend": trend,
        "last_swing_high": last_swing_high,
        "last_swing_low": last_swing_low,
        "last_bos": last_bos,
        "last_choch": last_choch,
    }
