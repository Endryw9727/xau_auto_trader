"""
Smart Money Concepts analyzer.

Aggregates FVG, Order Blocks, and Liquidity Sweeps into a unified analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.strategy.smart_money.fvg import FairValueGap, get_recent_fvg
from src.strategy.smart_money.liquidity import LiquiditySweep, get_recent_sweeps
from src.strategy.smart_money.order_blocks import OrderBlock, get_recent_order_blocks

@dataclass(frozen=True)
class SmartMoneyAnalysis:
    """Complete Smart Money analysis."""

    fvgs: list[FairValueGap]
    order_blocks: list[OrderBlock]
    liquidity_sweeps: list[LiquiditySweep]
    bias: str  # "BULLISH", "BEARISH", "NEUTRAL"
    key_support: float | None
    key_resistance: float | None
    explanation: str

def analyze_smart_money(df: pd.DataFrame, lookback: int = 50) -> SmartMoneyAnalysis:
    """
    Run complete Smart Money analysis on price data.

    Parameters:
    - df: OHLCV DataFrame
    - lookback: number of candles to analyze

    Returns:
    - SmartMoneyAnalysis with all concepts
    """
    fvgs = get_recent_fvg(df, lookback)
    obs = get_recent_order_blocks(df, lookback)
    sweeps = get_recent_sweeps(df, lookback)

    # Determine bias
    bullish_signals = sum(1 for f in fvgs if f.type == "BULLISH") + sum(1 for s in sweeps if s.type == "BULLISH_SWEEP")
    bearish_signals = sum(1 for f in fvgs if f.type == "BEARISH") + sum(1 for s in sweeps if s.type == "BEARISH_SWEEP")

    if bullish_signals > bearish_signals * 1.5:
        bias = "BULLISH"
    elif bearish_signals > bullish_signals * 1.5:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    # Key levels from OBs
    key_support = None
    key_resistance = None

    bullish_obs = [ob for ob in obs if ob.type == "BULLISH"]
    bearish_obs = [ob for ob in obs if ob.type == "BEARISH"]

    if bullish_obs:
        key_support = min(ob.low for ob in bullish_obs)
    if bearish_obs:
        key_resistance = max(ob.high for ob in bearish_obs)

    # Build explanation
    parts = [
        f"FVGs: {len(fvgs)} ({sum(1 for f in fvgs if f.type == 'BULLISH')} bullish, {sum(1 for f in fvgs if f.type == 'BEARISH')} bearish)",
        f"Order Blocks: {len(obs)} ({sum(1 for o in obs if o.type == 'BULLISH')} bullish, {sum(1 for o in obs if o.type == 'BEARISH')} bearish)",
        f"Liquidity Sweeps: {len(sweeps)} ({sum(1 for s in sweeps if s.type == 'BULLISH_SWEEP')} bullish, {sum(1 for s in sweeps if s.type == 'BEARISH_SWEEP')} bearish)",
        f"Bias: {bias}",
    ]
    if key_support:
        parts.append(f"Key Support: {key_support:.2f}")
    if key_resistance:
        parts.append(f"Key Resistance: {key_resistance:.2f}")

    return SmartMoneyAnalysis(
        fvgs=fvgs,
        order_blocks=obs,
        liquidity_sweeps=sweeps,
        bias=bias,
        key_support=key_support,
        key_resistance=key_resistance,
        explanation=" | ".join(parts),
    )

def smart_money_to_dict(analysis: SmartMoneyAnalysis) -> dict[str, Any]:
    """Convert SmartMoneyAnalysis to dictionary."""
    return {
        "bias": analysis.bias,
        "key_support": round(analysis.key_support, 2) if analysis.key_support else None,
        "key_resistance": round(analysis.key_resistance, 2) if analysis.key_resistance else None,
        "explanation": analysis.explanation,
        "fvgs": [fvg_to_dict(f) for f in analysis.fvgs[-5:]],
        "order_blocks": [ob_to_dict(o) for o in analysis.order_blocks[-5:]],
        "liquidity_sweeps": [sweep_to_dict(s) for s in analysis.liquidity_sweeps[-5:]],
    }

# Import helpers to avoid circular imports in to_dict
from src.strategy.smart_money.fvg import fvg_to_dict
from src.strategy.smart_money.liquidity import sweep_to_dict
from src.strategy.smart_money.order_blocks import ob_to_dict
