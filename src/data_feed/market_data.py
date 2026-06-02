"""
Market data loading utilities.

This module handles loading OHLCV data from CSV files.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

def load_csv_data(csv_path: str | Path) -> pd.DataFrame:
    """
    Load OHLCV data from a CSV file.

    Expected columns:
    Date, Open, High, Low, Close, Volume

    The Date column is parsed as datetime and set as index.
    """
    path = Path(csv_path)

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    df = pd.read_csv(
        path,
        parse_dates=["Date"],
        index_col="Date",
    )

    required_columns = ["Open", "High", "Low", "Close", "Volume"]
    missing = [col for col in required_columns if col not in df.columns]

    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df.sort_index()

    return df

def resample_data(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    Resample OHLCV data to a different timeframe.

    Parameters:
    - df: OHLCV DataFrame with DatetimeIndex
    - timeframe: pandas offset string (e.g. '15min', '1H', '4H', '1D')

    Returns:
    - Resampled DataFrame
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have a DatetimeIndex")

    resampled = df.resample(timeframe).agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    })

    resampled = resampled.dropna()

    return resampled

def check_data_freshness(df: pd.DataFrame, max_age_minutes: int = 30) -> dict:
    """
    Check if the data is fresh enough.

    Returns:
    - dict with 'is_fresh', 'last_candle_time', 'age_minutes'
    """
    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return {"is_fresh": False, "last_candle_time": None, "age_minutes": None}

    last_candle = df.index[-1]
    now = pd.Timestamp.now(tz=last_candle.tz)
    age = (now - last_candle).total_seconds() / 60

    return {
        "is_fresh": age <= max_age_minutes,
        "last_candle_time": last_candle,
        "age_minutes": age,
    }
