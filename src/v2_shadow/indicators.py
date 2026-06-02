"""V2-inspired core indicators for read-only shadow comparison."""

from __future__ import annotations

import pandas as pd


def add_ema(df: pd.DataFrame, period: int, column: str = "Close") -> pd.DataFrame:
    """Return a copy with a causal EMA column."""
    _validate_column(df, column)
    _validate_period(period)
    result = df.copy()
    result[f"v2_shadow_ema_{period}"] = result[column].ewm(span=period, adjust=False).mean()
    return result


def add_rsi(df: pd.DataFrame, period: int = 14, column: str = "Close") -> pd.DataFrame:
    """Return a copy with a causal RSI column."""
    _validate_column(df, column)
    _validate_period(period)
    result = df.copy()
    delta = result[column].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    result[f"v2_shadow_rsi_{period}"] = 100 - (100 / (1 + rs))
    return result


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Return a copy with a causal ATR column."""
    _validate_ohlc(df)
    _validate_period(period)
    result = df.copy()
    high_low = result["High"] - result["Low"]
    high_close_prev = (result["High"] - result["Close"].shift(1)).abs()
    low_close_prev = (result["Low"] - result["Close"].shift(1)).abs()
    true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
    result[f"v2_shadow_atr_{period}"] = true_range.ewm(alpha=1 / period, adjust=False).mean()
    return result


def add_macd(
    df: pd.DataFrame,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    column: str = "Close",
) -> pd.DataFrame:
    """Return a copy with causal MACD columns."""
    _validate_column(df, column)
    _validate_period(fast_period)
    _validate_period(slow_period)
    _validate_period(signal_period)
    if fast_period >= slow_period:
        raise ValueError("fast_period must be lower than slow_period")
    result = df.copy()
    fast = result[column].ewm(span=fast_period, adjust=False).mean()
    slow = result[column].ewm(span=slow_period, adjust=False).mean()
    result["v2_shadow_macd"] = fast - slow
    result["v2_shadow_macd_signal"] = result["v2_shadow_macd"].ewm(span=signal_period, adjust=False).mean()
    result["v2_shadow_macd_hist"] = result["v2_shadow_macd"] - result["v2_shadow_macd_signal"]
    return result


def add_core_shadow_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add the isolated V2 core-indicator comparison set."""
    result = df.copy()
    result = add_ema(result, 20)
    result = add_ema(result, 50)
    result = add_ema(result, 200)
    result = add_rsi(result, 14)
    result = add_atr(result, 14)
    result = add_macd(result)
    return result


def latest_indicator_snapshot(df: pd.DataFrame) -> dict[str, float | None]:
    """Return a compact latest-row indicator snapshot."""
    if df.empty:
        return {}
    latest = df.iloc[-1]
    keys = [
        "v2_shadow_ema_20",
        "v2_shadow_ema_50",
        "v2_shadow_ema_200",
        "v2_shadow_rsi_14",
        "v2_shadow_atr_14",
        "v2_shadow_macd",
        "v2_shadow_macd_signal",
        "v2_shadow_macd_hist",
    ]
    return {key: _float_or_none(latest.get(key)) for key in keys}


def _validate_column(df: pd.DataFrame, column: str) -> None:
    if column not in df.columns:
        raise ValueError(f"Missing required column: {column}")


def _validate_ohlc(df: pd.DataFrame) -> None:
    missing = [column for column in ("Open", "High", "Low", "Close") if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required OHLC columns: {missing}")


def _validate_period(period: int) -> None:
    if period <= 0:
        raise ValueError("period must be greater than 0")


def _float_or_none(value: object) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
