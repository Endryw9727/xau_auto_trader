"""
Market data loading and preprocessing utilities.

This module loads OHLCV data from CSV files and prepares it for:
- indicators
- strategy rules
- backtesting
- paper trading simulation

Expected CSV columns:
Date, Open, High, Low, Close, Volume
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]


def load_csv_data(file_path: str | Path) -> pd.DataFrame:
    """
    Load OHLCV market data from a CSV file.

    The CSV must contain:
    Date, Open, High, Low, Close, Volume

    Returns a clean DataFrame indexed by Date.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    df = pd.read_csv(path)

    validate_ohlcv_columns(df)

    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    numeric_columns = ["Open", "High", "Low", "Close", "Volume"]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.dropna(subset=REQUIRED_COLUMNS)
    df = df.drop_duplicates(subset=["Date"])
    df = df.sort_values("Date")
    df = df.set_index("Date")

    return df


def validate_ohlcv_columns(df: pd.DataFrame) -> None:
    """Validate that the DataFrame contains required OHLCV columns."""
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]

    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    Resample OHLCV data to a different timeframe.

    Examples:
    - 5min
    - 15min
    - 30min
    - 1h
    - 4h
    - 1D
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have a DatetimeIndex before resampling.")

    aggregation = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }

    resampled = df.resample(timeframe).agg(aggregation)
    resampled = resampled.dropna()

    return resampled


def get_latest_candles(df: pd.DataFrame, count: int = 100) -> pd.DataFrame:
    """Return the latest candles from the DataFrame."""
    if count <= 0:
        raise ValueError("count must be greater than 0")

    return df.tail(count).copy()


def save_processed_data(df: pd.DataFrame, file_path: str | Path) -> None:
    """Save processed market data to CSV."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(path, index=True)
