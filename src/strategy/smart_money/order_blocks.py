"""
Order Blocks (OB) detector.

Order Block = ultima candela contraria prima di un movimento impulsivo.
Bullish OB: candela bearish prima di un movimento rialzista.
Bearish OB: candela rialzista prima di un movimento ribassista.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

OBType = Literal["BULLISH", "BEARISH"]

@dataclass(frozen=True)
class OrderBlock:
    """Represents an Order Block."""

    type: OBType
    time: pd.Timestamp
    open_price: float
    high: float
    low: float
    close: float
    breaker: bool = False  # True if OB has been broken

def detect_order_blocks(df: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    """
    Detect Order Blocks.

    Adds columns:
    - ob_bullish: True if bullish OB at this candle
    - ob_bearish: True if bearish OB at this candle
    """
    result = df.copy()
    result["ob_bullish"] = pd.Series([False] * len(result), index=result.index, dtype=object)
    result["ob_bearish"] = pd.Series([False] * len(result), index=result.index, dtype=object)

    if len(result) < lookback + 2:
        return result

    for i in range(lookback, len(result) - 1):
        # Bullish OB: bearish candle followed by strong bullish move
        current = result.iloc[i]
        next_candle = result.iloc[i + 1]

        # Bearish candle (close < open)
        is_bearish = current["Close"] < current["Open"]
        # Next candle strong bullish (close > open and large range)
        next_bullish = next_candle["Close"] > next_candle["Open"]
        next_range = next_candle["High"] - next_candle["Low"]
        avg_range = result["High"].iloc[i - lookback:i].mean() - result["Low"].iloc[i - lookback:i].mean()

        if is_bearish and next_bullish and next_range > avg_range * 1.2:
            result.at[result.index[i], "ob_bullish"] = True

        # Bearish OB: bullish candle followed by strong bearish move
        is_bullish = current["Close"] > current["Open"]
        next_bearish = next_candle["Close"] < next_candle["Open"]

        if is_bullish and next_bearish and next_range > avg_range * 1.2:
            result.at[result.index[i], "ob_bearish"] = True

    return result

def get_recent_order_blocks(df: pd.DataFrame, lookback: int = 50) -> list[OrderBlock]:
    """Get recent order blocks."""
    result = detect_order_blocks(df, lookback=min(5, lookback // 10))
    recent = result.iloc[-lookback:]

    obs = []
    for idx, row in recent.iterrows():
        if row["ob_bullish"]:
            obs.append(OrderBlock(
                type="BULLISH",
                time=idx,
                open_price=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
            ))
        elif row["ob_bearish"]:
            obs.append(OrderBlock(
                type="BEARISH",
                time=idx,
                open_price=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
            ))

    return obs

def ob_to_dict(ob: OrderBlock) -> dict:
    """Convert Order Block to dictionary."""
    return {
        "type": ob.type,
        "time": str(ob.time),
        "open": round(ob.open_price, 2),
        "high": round(ob.high, 2),
        "low": round(ob.low, 2),
        "close": round(ob.close, 2),
        "breaker": ob.breaker,
    }
