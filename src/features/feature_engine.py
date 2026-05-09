"""
Feature engine for XAU Auto Trader research.

This module builds deterministic, pandas-based features for backtesting and
analysis only. It does not execute trades and does not interact with brokers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.analysis.session_analysis import classify_hour_to_session
from src.strategy.indicators import add_all_core_indicators


WILLIAMS_R_PERIOD = 14
VOLATILITY_LOOKBACK = 50
LOW_VOL_MULTIPLIER = 0.75
HIGH_VOL_MULTIPLIER = 1.25
IMPULSE_BODY_RATIO = 0.65
INDECISION_BODY_RATIO = 0.25


def build_features(data: pd.DataFrame) -> pd.DataFrame:
    """
    Build a feature DataFrame from OHLCV market data.

    The function preserves the input index and row count. Indicator warmup or
    flat-price edge cases may create NaN values, but rows are not dropped.
    """
    _validate_ohlcv(data)

    result = add_all_core_indicators(data)

    result["ema_20"] = result["EMA_20"]
    result["ema_50"] = result["EMA_50"]
    result["ema_200"] = result["EMA_200"]
    result["ema_20_slope"] = result["ema_20"].diff()
    result["ema_50_slope"] = result["ema_50"].diff()
    result["rsi"] = result["RSI_14"]
    result["adx"] = result["ADX_14"]
    result["atr"] = result["ATR_14"]
    result["atr_ratio"] = _safe_divide(result["atr"], result["Close"])
    result["williams_r"] = _calculate_williams_r(result)

    result["candle_body"] = (result["Close"] - result["Open"]).abs()
    result["candle_range"] = result["High"] - result["Low"]
    result["body_to_range_ratio"] = _safe_divide(result["candle_body"], result["candle_range"])

    upper_wick = result["High"] - result[["Open", "Close"]].max(axis=1)
    lower_wick = result[["Open", "Close"]].min(axis=1) - result["Low"]

    result["upper_wick_ratio"] = _safe_divide(upper_wick.clip(lower=0.0), result["candle_range"])
    result["lower_wick_ratio"] = _safe_divide(lower_wick.clip(lower=0.0), result["candle_range"])
    result["distance_from_ema20"] = _safe_divide(result["Close"] - result["ema_20"], result["atr"])
    result["distance_from_ema50"] = _safe_divide(result["Close"] - result["ema_50"], result["atr"])

    _add_time_features(result)

    result["trend_regime"] = result.apply(classify_trend_regime, axis=1)
    result["volatility_regime"] = classify_volatility_regime(result["atr_ratio"])
    result["candle_regime"] = result.apply(classify_candle_regime, axis=1)

    return result.replace([np.inf, -np.inf], np.nan)


def classify_trend_regime(row: pd.Series) -> str:
    """Classify trend as bullish, bearish, or neutral."""
    required = ["ema_20", "ema_50", "ema_200", "ema_20_slope", "ema_50_slope"]

    if any(column not in row.index or pd.isna(row[column]) for column in required):
        return "neutral"

    bullish_stack = row["ema_20"] > row["ema_50"] > row["ema_200"]
    bearish_stack = row["ema_20"] < row["ema_50"] < row["ema_200"]

    if bullish_stack and row["ema_20_slope"] > 0 and row["ema_50_slope"] >= 0:
        return "bullish"

    if bearish_stack and row["ema_20_slope"] < 0 and row["ema_50_slope"] <= 0:
        return "bearish"

    return "neutral"


def classify_volatility_regime(atr_ratio: pd.Series) -> pd.Series:
    """Classify ATR ratio as low, normal, or high volatility."""
    rolling_baseline = atr_ratio.rolling(
        window=VOLATILITY_LOOKBACK,
        min_periods=1,
    ).median()

    low_threshold = rolling_baseline * LOW_VOL_MULTIPLIER
    high_threshold = rolling_baseline * HIGH_VOL_MULTIPLIER

    regimes = pd.Series("normal", index=atr_ratio.index, dtype="object")
    regimes = regimes.mask(atr_ratio < low_threshold, "low")
    regimes = regimes.mask(atr_ratio > high_threshold, "high")
    regimes = regimes.mask(atr_ratio.isna(), "normal")

    return regimes


def classify_candle_regime(row: pd.Series) -> str:
    """Classify candle shape as impulse, normal, or indecision."""
    if "body_to_range_ratio" not in row.index or pd.isna(row["body_to_range_ratio"]):
        return "normal"

    ratio = float(row["body_to_range_ratio"])

    if ratio >= IMPULSE_BODY_RATIO:
        return "impulse"

    if ratio <= INDECISION_BODY_RATIO:
        return "indecision"

    return "normal"


def _calculate_williams_r(data: pd.DataFrame, period: int = WILLIAMS_R_PERIOD) -> pd.Series:
    """Calculate Williams %R."""
    highest_high = data["High"].rolling(window=period, min_periods=period).max()
    lowest_low = data["Low"].rolling(window=period, min_periods=period).min()
    denominator = highest_high - lowest_low

    return -100.0 * _safe_divide(highest_high - data["Close"], denominator)


def _add_time_features(result: pd.DataFrame) -> None:
    """Add session, hour, and day-of-week features in place."""
    if not isinstance(result.index, pd.DatetimeIndex):
        result["hour"] = np.nan
        result["day_of_week"] = np.nan
        result["session"] = "Unknown"
        return

    result["hour"] = result.index.hour
    result["day_of_week"] = result.index.dayofweek
    result["session"] = result["hour"].apply(lambda hour: classify_hour_to_session(int(hour)))


def _safe_divide(numerator, denominator) -> pd.Series:
    """Divide while converting zero denominators and infinities to NaN."""
    denominator_series = pd.Series(denominator).replace(0, np.nan)
    result = pd.Series(numerator, index=denominator_series.index) / denominator_series

    return result.replace([np.inf, -np.inf], np.nan)


def _validate_ohlcv(data: pd.DataFrame) -> None:
    """Validate required OHLCV columns."""
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in data.columns]

    if missing:
        raise ValueError(f"Missing required OHLCV columns: {missing}")
