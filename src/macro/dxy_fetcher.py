"""
DXY (US Dollar Index) fetcher.

Fetches DXY data from Yahoo Finance and calculates trend bias.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
import yfinance as yf

MacroBias = Literal["BULLISH", "BEARISH", "NEUTRAL"]

def fetch_dxy(period: str = "5d", interval: str = "15m") -> pd.DataFrame:
    """Fetch DXY data from Yahoo Finance."""
    try:
        ticker = yf.Ticker("DX-Y.NYB")
        df = ticker.history(period=period, interval=interval)
        return df
    except Exception as e:
        raise RuntimeError(f"Failed to fetch DXY: {e}")

def get_dxy_bias(df: pd.DataFrame, fast_ema: int = 20, slow_ema: int = 50) -> MacroBias:
    """Determine DXY trend bias from EMA cross."""
    if df.empty or "Close" not in df.columns:
        return "NEUTRAL"

    df = df.copy()
    df["EMA_fast"] = df["Close"].ewm(span=fast_ema, adjust=False).mean()
    df["EMA_slow"] = df["Close"].ewm(span=slow_ema, adjust=False).mean()

    last = df.iloc[-1]
    if last["EMA_fast"] > last["EMA_slow"]:
        return "BULLISH"
    elif last["EMA_fast"] < last["EMA_slow"]:
        return "BEARISH"
    return "NEUTRAL"

def get_dxy_current_value(df: pd.DataFrame) -> float | None:
    """Get current DXY value."""
    if df.empty or "Close" not in df.columns:
        return None
    return float(df["Close"].iloc[-1])
