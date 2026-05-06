"""
Technical indicators used by the trading strategy.

All functions are pure pandas-based utilities.
They receive an OHLCV DataFrame and return a new DataFrame with added columns.

Required columns for most indicators:
Open, High, Low, Close, Volume
"""

from __future__ import annotations

import pandas as pd


def add_ema(df: pd.DataFrame, period: int, column: str = "Close") -> pd.DataFrame:
    """Add an Exponential Moving Average column."""
    _validate_column(df, column)
    _validate_period(period)

    result = df.copy()
    result[f"EMA_{period}"] = result[column].ewm(span=period, adjust=False).mean()
    return result


def add_rsi(df: pd.DataFrame, period: int = 14, column: str = "Close") -> pd.DataFrame:
    """Add RSI indicator column."""
    _validate_column(df, column)
    _validate_period(period)

    result = df.copy()

    delta = result[column].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss
    result[f"RSI_{period}"] = 100 - (100 / (1 + rs))

    return result


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add Average True Range indicator column."""
    _validate_ohlc(df)
    _validate_period(period)

    result = df.copy()

    high_low = result["High"] - result["Low"]
    high_close_prev = (result["High"] - result["Close"].shift(1)).abs()
    low_close_prev = (result["Low"] - result["Close"].shift(1)).abs()

    true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
    result[f"ATR_{period}"] = true_range.ewm(alpha=1 / period, adjust=False).mean()

    return result


def add_macd(
    df: pd.DataFrame,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    column: str = "Close",
) -> pd.DataFrame:
    """Add MACD, MACD signal, and MACD histogram columns."""
    _validate_column(df, column)
    _validate_period(fast_period)
    _validate_period(slow_period)
    _validate_period(signal_period)

    if fast_period >= slow_period:
        raise ValueError("fast_period must be lower than slow_period")

    result = df.copy()

    fast_ema = result[column].ewm(span=fast_period, adjust=False).mean()
    slow_ema = result[column].ewm(span=slow_period, adjust=False).mean()

    result["MACD"] = fast_ema - slow_ema
    result["MACD_SIGNAL"] = result["MACD"].ewm(span=signal_period, adjust=False).mean()
    result["MACD_HIST"] = result["MACD"] - result["MACD_SIGNAL"]

    return result


def add_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Add ADX, +DI and -DI columns.

    ADX helps measure trend strength.
    It does not tell direction alone; direction comes from +DI and -DI.
    """
    _validate_ohlc(df)
    _validate_period(period)

    result = df.copy()

    high = result["High"]
    low = result["Low"]
    close = result["Close"]

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

    result[f"PLUS_DI_{period}"] = plus_di
    result[f"MINUS_DI_{period}"] = minus_di
    result[f"ADX_{period}"] = adx

    return result


def add_all_core_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a standard set of indicators used by the first strategy version.

    This is useful for backtesting and signal generation.
    """
    result = df.copy()

    result = add_ema(result, 20)
    result = add_ema(result, 50)
    result = add_ema(result, 200)
    result = add_rsi(result, 14)
    result = add_atr(result, 14)
    result = add_macd(result)
    result = add_adx(result, 14)

    return result


def _validate_column(df: pd.DataFrame, column: str) -> None:
    """Validate that a DataFrame contains a specific column."""
    if column not in df.columns:
        raise ValueError(f"Missing required column: {column}")


def _validate_ohlc(df: pd.DataFrame) -> None:
    """Validate that a DataFrame contains OHLC columns."""
    required = ["Open", "High", "Low", "Close"]
    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"Missing required OHLC columns: {missing}")


def _validate_period(period: int) -> None:
    """Validate indicator period."""
    if period <= 0:
        raise ValueError("period must be greater than 0")
