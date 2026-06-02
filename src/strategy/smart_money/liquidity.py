"""
Liquidity sweep detector.

Liquidity sweep = prelievo di stops al di sopra/basso di swing highs/lows
prima di un movimento reale nella direzione opposta.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

SweepType = Literal["BULLISH_SWEEP", "BEARISH_SWEEP"]

@dataclass(frozen=True)
class LiquiditySweep:
    """Represents a liquidity sweep."""

    type: SweepType
    time: pd.Timestamp
    swept_level: float
    price_after_sweep: float
    confirmed: bool

def detect_liquidity_sweeps(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    Detect liquidity sweeps above/below recent swing levels.

    Adds columns:
    - sweep_bullish: True if bullish sweep (sweeps below swing low then reverses up)
    - sweep_bearish: True if bearish sweep (sweeps above swing high then reverses down)
    """
    result = df.copy()
    result["sweep_bullish"] = pd.Series([False] * len(result), index=result.index, dtype=object)
    result["sweep_bearish"] = pd.Series([False] * len(result), index=result.index, dtype=object)
    result["swept_level"] = float("nan")

    if len(result) < window * 2 + 2:
        return result

    for i in range(window, len(result) - 1):
        # Recent range
        recent_highs = result["High"].iloc[i - window:i]
        recent_lows = result["Low"].iloc[i - window:i]

        swing_high = recent_highs.max()
        swing_low = recent_lows.min()

        current_high = result["High"].iloc[i]
        current_low = result["Low"].iloc[i]
        next_close = result["Close"].iloc[i + 1]

        # Bearish sweep: price goes above swing high but closes back below
        if current_high > swing_high and next_close < swing_high:
            result.at[result.index[i], "sweep_bearish"] = True
            result.at[result.index[i], "swept_level"] = swing_high

        # Bullish sweep: price goes below swing low but closes back above
        if current_low < swing_low and next_close > swing_low:
            result.at[result.index[i], "sweep_bullish"] = True
            result.at[result.index[i], "swept_level"] = swing_low

    return result

def get_recent_sweeps(df: pd.DataFrame, lookback: int = 20) -> list[LiquiditySweep]:
    """Get recent liquidity sweeps."""
    result = detect_liquidity_sweeps(df)
    recent = result.iloc[-lookback:]

    sweeps = []
    for idx, row in recent.iterrows():
        if row["sweep_bullish"]:
            sweeps.append(LiquiditySweep(
                type="BULLISH_SWEEP",
                time=idx,
                swept_level=float(row["swept_level"]),
                price_after_sweep=float(result.loc[idx:].iloc[1]["Close"]) if len(result.loc[idx:]) > 1 else float(row["Close"]),
                confirmed=True,
            ))
        elif row["sweep_bearish"]:
            sweeps.append(LiquiditySweep(
                type="BEARISH_SWEEP",
                time=idx,
                swept_level=float(row["swept_level"]),
                price_after_sweep=float(result.loc[idx:].iloc[1]["Close"]) if len(result.loc[idx:]) > 1 else float(row["Close"]),
                confirmed=True,
            ))

    return sweeps

def sweep_to_dict(sweep: LiquiditySweep) -> dict:
    """Convert liquidity sweep to dictionary."""
    return {
        "type": sweep.type,
        "time": str(sweep.time),
        "swept_level": round(sweep.swept_level, 2),
        "price_after": round(sweep.price_after_sweep, 2),
        "confirmed": sweep.confirmed,
    }
