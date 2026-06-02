"""
Market regime detector.

Classifies current market conditions into regimes:
- TRENDING_UP
- TRENDING_DOWN
- RANGING
- VOLATILE
- LOW_VOLATILITY
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from src.strategy.indicators import add_adx, add_atr

Regime = Literal["TRENDING_UP", "TRENDING_DOWN", "RANGING", "VOLATILE", "LOW_VOLATILITY"]

@dataclass(frozen=True)
class RegimeAnalysis:
    regime: Regime
    adx: float
    atr_pct: float
    volatility_regime: str
    trend_strength: str
    recommendation: str


def detect_regime(df: pd.DataFrame, lookback: int = 50) -> RegimeAnalysis:
    if len(df) < lookback:
        return RegimeAnalysis("RANGING", 0.0, 0.0, "unknown", "weak", "Wait for clearer setup")

    recent = df.iloc[-lookback:]

    df_adx = add_adx(df.copy(), period=14)
    adx = float(df_adx["ADX_14"].iloc[-1]) if not df_adx["ADX_14"].isna().iloc[-1] else 0.0

    df_atr = add_atr(df.copy(), period=14)
    atr = float(df_atr["ATR_14"].iloc[-1]) if not df_atr["ATR_14"].isna().iloc[-1] else 0.0
    current_price = float(df["Close"].iloc[-1])
    atr_pct = (atr / current_price) * 100 if current_price > 0 else 0.0

    price_change = (recent["Close"].iloc[-1] - recent["Close"].iloc[0]) / recent["Close"].iloc[0] * 100

    if atr_pct > 0.5:
        volatility_regime = "high"
    elif atr_pct > 0.2:
        volatility_regime = "medium"
    else:
        volatility_regime = "low"

    if adx >= 30:
        trend_strength = "strong"
    elif adx >= 20:
        trend_strength = "moderate"
    else:
        trend_strength = "weak"

    if adx >= 25 and abs(price_change) > 2.0:
        if price_change > 0:
            regime = "TRENDING_UP"
            recommendation = "Favor long setups with trend following"
        else:
            regime = "TRENDING_DOWN"
            recommendation = "Favor short setups with trend following"
    elif adx < 20 and atr_pct < 0.3:
        regime = "RANGING"
        recommendation = "Use mean-reversion or wait for breakout"
    elif atr_pct > 0.6:
        regime = "VOLATILE"
        recommendation = "Reduce size, widen stops, or stay flat"
    else:
        regime = "LOW_VOLATILITY"
        recommendation = "Low opportunity — reduce frequency or size"

    return RegimeAnalysis(
        regime=regime,
        adx=round(adx, 1),
        atr_pct=round(atr_pct, 2),
        volatility_regime=volatility_regime,
        trend_strength=trend_strength,
        recommendation=recommendation,
    )
