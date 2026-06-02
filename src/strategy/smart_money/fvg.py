"""
Fair Value Gaps (FVG) detector.

FVG = inefficienza di prezzo dove non c'è stato overlap tra le candele.
Un FVG bullish: Low della candela corrente > High della candela 2 posizioni prima.
Un FVG bearish: High della candela corrente < Low della candela 2 posizioni prima.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

FVGType = Literal["BULLISH", "BEARISH"]

@dataclass(frozen=True)
class FairValueGap:
    """Represents a Fair Value Gap."""

    type: FVGType
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    top: float
    bottom: float
    size: float

def detect_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect Fair Value Gaps in OHLCV data.

    Adds columns:
    - fvg_bullish: True if bullish FVG at this candle
    - fvg_bearish: True if bearish FVG at this candle
    - fvg_top: top of the FVG
    - fvg_bottom: bottom of the FVG
    """
    if len(df) < 3:
        return df.copy()

    result = df.copy()
    result["fvg_bullish"] = pd.Series([False] * len(result), index=result.index, dtype=object)
    result["fvg_bearish"] = pd.Series([False] * len(result), index=result.index, dtype=object)
    result["fvg_top"] = float("nan")
    result["fvg_bottom"] = float("nan")

    for i in range(2, len(result)):
        # Bullish FVG: current Low > High of candle i-2
        if result["Low"].iloc[i] > result["High"].iloc[i - 2]:
            result.at[result.index[i], "fvg_bullish"] = True
            result.at[result.index[i], "fvg_top"] = result["Low"].iloc[i]
            result.at[result.index[i], "fvg_bottom"] = result["High"].iloc[i - 2]

        # Bearish FVG: current High < Low of candle i-2
        if result["High"].iloc[i] < result["Low"].iloc[i - 2]:
            result.at[result.index[i], "fvg_bearish"] = True
            result.at[result.index[i], "fvg_top"] = result["Low"].iloc[i - 2]
            result.at[result.index[i], "fvg_bottom"] = result["High"].iloc[i]

    return result

def get_recent_fvg(df: pd.DataFrame, lookback: int = 20) -> list[FairValueGap]:
    """Get recent FVGs from the last N candles."""
    if len(df) < 3:
        return []

    result = detect_fvg(df)
    recent = result.iloc[-lookback:]

    fvgs = []
    for idx, row in recent.iterrows():
        if row["fvg_bullish"]:
            fvgs.append(FairValueGap(
                type="BULLISH",
                start_time=idx,
                end_time=idx,
                top=float(row["fvg_top"]),
                bottom=float(row["fvg_bottom"]),
                size=float(row["fvg_top"] - row["fvg_bottom"]),
            ))
        elif row["fvg_bearish"]:
            fvgs.append(FairValueGap(
                type="BEARISH",
                start_time=idx,
                end_time=idx,
                top=float(row["fvg_top"]),
                bottom=float(row["fvg_bottom"]),
                size=float(row["fvg_top"] - row["fvg_bottom"]),
            ))

    return fvgs

def fvg_to_dict(fvg: FairValueGap) -> dict:
    """Convert FVG to dictionary."""
    return {
        "type": fvg.type,
        "start_time": str(fvg.start_time),
        "top": round(fvg.top, 2),
        "bottom": round(fvg.bottom, 2),
        "size": round(fvg.size, 2),
    }
