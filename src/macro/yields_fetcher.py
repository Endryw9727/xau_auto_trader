"""
US Treasury 10Y yield fetcher.

Fetches US10Y data from Yahoo Finance.
Rising yields = bearish for gold (opportunity cost).
Falling yields = bullish for gold.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
import yfinance as yf

MacroBias = Literal["BULLISH", "BEARISH", "NEUTRAL"]

def fetch_us10y(period: str = "5d", interval: str = "15m") -> pd.DataFrame:
    """Fetch US10Y data from Yahoo Finance."""
    try:
        ticker = yf.Ticker("^TNX")
        df = ticker.history(period=period, interval=interval)
        return df
    except Exception as e:
        raise RuntimeError(f"Failed to fetch US10Y: {e}")

def get_yield_bias(df: pd.DataFrame, fast_ema: int = 20, slow_ema: int = 50) -> MacroBias:
    """Determine yield trend bias."""
    if df.empty or "Close" not in df.columns:
        return "NEUTRAL"

    df = df.copy()
    df["EMA_fast"] = df["Close"].ewm(span=fast_ema, adjust=False).mean()
    df["EMA_slow"] = df["Close"].ewm(span=slow_ema, adjust=False).mean()

    last = df.iloc[-1]
    if last["EMA_fast"] > last["EMA_slow"]:
        return "BULLISH"  # Rising yields = bearish gold, but we return yield bias
    elif last["EMA_fast"] < last["EMA_slow"]:
        return "BEARISH"
    return "NEUTRAL"

def get_yield_current_value(df: pd.DataFrame) -> float | None:
    """Get current yield value."""
    if df.empty or "Close" not in df.columns:
        return None
    return float(df["Close"].iloc[-1])
