"""
Multi-timeframe feature builder for the Pine V50 research translation.

The base dataframe is M5. Higher timeframe features are shifted before
merge_asof alignment, so M5 rows only see already closed higher-timeframe
candles. This module is local research/backtest only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


REQUIRED_TIMEFRAMES = ("M5", "M15", "H1", "H4")
HIGHER_TIMEFRAME_SPECS = {
    "10": ("M10", "10min"),
    "15": ("M15", None),
    "1h": ("H1", None),
    "4h": ("H4", None),
}
INDICATOR_COLUMNS = [
    "close",
    "ema20",
    "ema21",
    "ema50",
    "ema200",
    "ema50_slope",
    "rsi",
    "williams_r",
    "plus_di",
    "minus_di",
    "adx",
    "atr",
    "candle_body",
    "candle_range",
    "body_to_range_ratio",
    "distance_from_ema20",
    "distance_from_ema50",
]


def build_v50_mtf_dataset(timeframes: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Build an anti-repaint MTF dataset using M5 as base.

    Required keys: M5, M15, H1, H4. If M10 is missing, it is resampled from M5.
    """
    _validate_timeframes(timeframes)

    normalized = {
        timeframe: _normalize_frame(frame, timeframe)
        for timeframe, frame in timeframes.items()
    }

    if "M10" not in normalized:
        normalized["M10"] = _resample_from_m5(normalized["M5"])

    base = _build_indicator_frame(normalized["M5"])
    base["session"] = base["time"].apply(_classify_v50_session)
    base["timeframe"] = "M5"
    base["volume_ok"] = True

    for suffix, (timeframe, _) in HIGHER_TIMEFRAME_SPECS.items():
        higher = _build_indicator_frame(normalized[timeframe])
        base = _merge_closed_timeframe(base, higher, suffix)

    base = _add_backtester_aliases(base)
    base = base.sort_values("time").reset_index(drop=True)
    base.index = pd.DatetimeIndex(base["time"], name="time")

    return base.replace([np.inf, -np.inf], np.nan).copy()


def _validate_timeframes(timeframes: dict[str, pd.DataFrame]) -> None:
    missing = [timeframe for timeframe in REQUIRED_TIMEFRAMES if timeframe not in timeframes]
    if missing:
        raise ValueError(f"Missing required timeframes: {missing}")


def _normalize_frame(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    required = ["time", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"{timeframe} missing columns: {missing}")

    result = frame.copy()
    result["time"] = pd.to_datetime(result["time"], errors="coerce")

    for column in ["open", "high", "low", "close", "volume"]:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    if "has_real_volume" not in result.columns:
        result["has_real_volume"] = False

    result["has_real_volume"] = result["has_real_volume"].fillna(False).astype(bool)
    result["timeframe"] = timeframe

    return (
        result.dropna(subset=["time", "open", "high", "low", "close"])
        .drop_duplicates(subset=["time"])
        .sort_values("time")
        .reset_index(drop=True)
    )


def _resample_from_m5(m5: pd.DataFrame) -> pd.DataFrame:
    indexed = m5.sort_values("time").set_index("time")
    resampled = (
        indexed[["open", "high", "low", "close", "volume"]]
        .resample("10min", label="right", closed="right")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )
    resampled["volume"] = 1.0
    resampled["timeframe"] = "M10"
    resampled["has_real_volume"] = False
    return resampled


def _build_indicator_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["ema20"] = result["close"].ewm(span=20, adjust=False).mean()
    result["ema21"] = result["close"].ewm(span=21, adjust=False).mean()
    result["ema50"] = result["close"].ewm(span=50, adjust=False).mean()
    result["ema200"] = result["close"].ewm(span=200, adjust=False).mean()
    result["ema50_slope"] = result["ema50"].diff(3)
    result["rsi"] = _calculate_rsi(result["close"])
    result["williams_r"] = _calculate_williams_r(result)
    result["atr"] = _calculate_atr(result)
    plus_di, minus_di, adx = _calculate_dmi_adx(result)
    result["plus_di"] = plus_di
    result["minus_di"] = minus_di
    result["adx"] = adx
    result["candle_body"] = (result["close"] - result["open"]).abs()
    result["candle_range"] = result["high"] - result["low"]
    result["body_to_range_ratio"] = _safe_divide(result["candle_body"], result["candle_range"])
    result["distance_from_ema20"] = _safe_divide(result["close"] - result["ema20"], result["atr"])
    result["distance_from_ema50"] = _safe_divide(result["close"] - result["ema50"], result["atr"])
    result["volume_ok"] = True
    return result


def _merge_closed_timeframe(base: pd.DataFrame, higher: pd.DataFrame, suffix: str) -> pd.DataFrame:
    value_columns = [column for column in INDICATOR_COLUMNS if column in higher.columns]
    shifted = higher[["time", *value_columns]].copy()
    shifted[value_columns] = shifted[value_columns].shift(1)
    shifted = shifted.rename(
        columns={
            column: f"{column}_{suffix}"
            for column in value_columns
        }
    )

    return pd.merge_asof(
        base.sort_values("time"),
        shifted.sort_values("time"),
        on="time",
        direction="backward",
        allow_exact_matches=True,
    )


def _add_backtester_aliases(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    result["Open"] = result["open"]
    result["High"] = result["high"]
    result["Low"] = result["low"]
    result["Close"] = result["close"]
    result["Volume"] = result["volume"]
    result["EMA_20"] = result["ema20"]
    result["EMA_50"] = result["ema50"]
    result["EMA_200"] = result["ema200"]
    result["RSI_14"] = result["rsi"]
    result["ATR_14"] = result["atr"]
    result["ADX_14"] = result["adx"]
    result["PLUS_DI_14"] = result["plus_di"]
    result["MINUS_DI_14"] = result["minus_di"]
    return result


def _calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _calculate_williams_r(data: pd.DataFrame, period: int = 24) -> pd.Series:
    highest_high = data["high"].rolling(period, min_periods=period).max()
    lowest_low = data["low"].rolling(period, min_periods=period).min()
    return -100.0 * _safe_divide(highest_high - data["close"], highest_high - lowest_low)


def _calculate_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = data["high"] - data["low"]
    high_close_prev = (data["high"] - data["close"].shift(1)).abs()
    low_close_prev = (data["low"] - data["close"].shift(1)).abs()
    true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False).mean()


def _calculate_dmi_adx(data: pd.DataFrame, period: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    high = data["high"]
    low = data["low"]
    close = data["close"]

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    high_low = high - low
    high_close_prev = (high - close.shift(1)).abs()
    low_close_prev = (low - close.shift(1)).abs()
    true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1 / period, adjust=False).mean()

    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return plus_di, minus_di, adx


def _safe_divide(numerator, denominator) -> pd.Series:
    numerator_series = pd.Series(numerator)
    denominator_series = pd.Series(denominator).replace(0, np.nan)
    return (numerator_series / denominator_series).replace([np.inf, -np.inf], np.nan)


def _classify_v50_session(timestamp: pd.Timestamp) -> str:
    hour = int(timestamp.hour)
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

