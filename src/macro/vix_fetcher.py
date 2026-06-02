"""
VIX (Volatility Index) fetcher.

VIX > 25 = high fear, potential safe-haven demand for gold.
VIX < 15 = low fear, risk-on environment.
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf

def fetch_vix(period: str = "5d", interval: str = "15m") -> pd.DataFrame:
    """Fetch VIX data from Yahoo Finance."""
    try:
        ticker = yf.Ticker("^VIX")
        df = ticker.history(period=period, interval=interval)
        return df
    except Exception as e:
        raise RuntimeError(f"Failed to fetch VIX: {e}")

def get_vix_level(df: pd.DataFrame) -> str:
    """Classify VIX level."""
    if df.empty or "Close" not in df.columns:
        return "unknown"

    value = float(df["Close"].iloc[-1])

    if value >= 30:
        return "extreme_fear"
    elif value >= 25:
        return "high_fear"
    elif value >= 20:
        return "elevated"
    elif value >= 15:
        return "normal"
    else:
        return "low"

def get_vix_current_value(df: pd.DataFrame) -> float | None:
    """Get current VIX value."""
    if df.empty or "Close" not in df.columns:
        return None
    return float(df["Close"].iloc[-1])
