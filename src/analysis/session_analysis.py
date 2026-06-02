"""
Session analysis for XAU/USD.

This module classifies timestamps into trading sessions:
- Asia (Tokyo)
- London
- New York
- Off Session (no major session active)
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

SessionType = Literal["Asia", "London", "New York", "Off Session"]

def classify_session(timestamp: pd.Timestamp) -> SessionType:
    """
    Classify a timestamp into a trading session.

    Uses UTC hour for simplicity:
    - Asia: 00:00 - 08:00 UTC
    - London: 08:00 - 16:00 UTC
    - New York: 13:00 - 21:00 UTC
    - Off Session: all other times
    """
    hour = timestamp.hour

    if 0 <= hour < 8:
        return "Asia"
    elif 8 <= hour < 16:
        return "London"
    elif 13 <= hour < 21:
        return "New York"
    else:
        return "Off Session"

def is_session_active(timestamp: pd.Timestamp, session: SessionType) -> bool:
    """Check if a specific session is active at the given timestamp."""
    return classify_session(timestamp) == session

def get_session_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get statistics per trading session from a DataFrame.

    The DataFrame must have a DatetimeIndex.
    """
    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return pd.DataFrame()

    df = df.copy()
    df["session"] = df.index.map(classify_session)

    stats = df.groupby("session").agg({
        "Close": ["mean", "std", "min", "max", "count"],
    })

    stats.columns = ["mean_close", "std_close", "min_close", "max_close", "candles"]
    stats = stats.reset_index()

    return stats
