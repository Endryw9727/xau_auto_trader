"""
Signal generation V2 with Smart Money Concepts confluence.

This module extends the base signal generation by adding:
- Fair Value Gap (FVG) confluence
- Order Block (OB) proximity
- Liquidity Sweep confirmation

A signal is strengthened if price is near a relevant FVG or OB,
or if a liquidity sweep has recently occurred in the signal direction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from src.strategy.indicators import add_all_core_indicators
from src.strategy.rules import (
    StrategyConfig,
    build_reason,
    calculate_trade_levels,
    get_trend_bias,
    is_adx_ok,
    is_rsi_ok_for_side,
)
from src.strategy.smart_money.fvg import detect_fvg, get_recent_fvg
from src.strategy.smart_money.liquidity import detect_liquidity_sweeps, get_recent_sweeps
from src.strategy.smart_money.order_blocks import detect_order_blocks, get_recent_order_blocks

SignalSide = Literal["BUY", "SELL", "NO_TRADE"]

@dataclass(frozen=True)
class SignalConfluence:
    """Confluence factors from Smart Money Concepts."""

    fvg_aligned: bool
    ob_nearby: bool
    liquidity_sweep_confirmed: bool
    smc_score: float  # 0.0 to 1.0
    explanation: str

def check_smc_confluence(
    df: pd.DataFrame,
    side: SignalSide,
    current_price: float,
    lookback: int = 20,
) -> SignalConfluence:
    """
    Check Smart Money Concepts confluence for a signal.

    Parameters:
    - df: OHLCV DataFrame
    - side: BUY or SELL
    - current_price: current price level
    - lookback: candles to look back

    Returns:
    - SignalConfluence with score and explanation
    """
    if side not in {"BUY", "SELL"}:
        return SignalConfluence(False, False, False, 0.0, "No trade side")

    df = detect_fvg(df)
    df = detect_order_blocks(df, lookback=min(5, lookback // 10))
    df = detect_liquidity_sweeps(df, window=3)

    fvgs = get_recent_fvg(df, lookback)
    obs = get_recent_order_blocks(df, lookback)
    sweeps = get_recent_sweeps(df, lookback)

    # FVG confluence
    fvg_aligned = False
    fvg_explanation = ""
    for fvg in fvgs:
        if side == "BUY" and fvg.type == "BULLISH":
            if current_price >= fvg.bottom and current_price <= fvg.top:
                fvg_aligned = True
                fvg_explanation = f"Inside bullish FVG [{fvg.bottom:.2f}-{fvg.top:.2f}]"
                break
        elif side == "SELL" and fvg.type == "BEARISH":
            if current_price >= fvg.bottom and current_price <= fvg.top:
                fvg_aligned = True
                fvg_explanation = f"Inside bearish FVG [{fvg.bottom:.2f}-{fvg.top:.2f}]"
                break

    # OB confluence
    ob_nearby = False
    ob_explanation = ""
    for ob in obs:
        if side == "BUY" and ob.type == "BULLISH":
            if abs(current_price - ob.low) / current_price < 0.002:  # Within 0.2%
                ob_nearby = True
                ob_explanation = f"Near bullish OB low {ob.low:.2f}"
                break
        elif side == "SELL" and ob.type == "BEARISH":
            if abs(current_price - ob.high) / current_price < 0.002:
                ob_nearby = True
                ob_explanation = f"Near bearish OB high {ob.high:.2f}"
                break

    # Liquidity sweep confirmation
    sweep_confirmed = False
    sweep_explanation = ""
    for sweep in sweeps:
        if side == "BUY" and sweep.type == "BULLISH_SWEEP":
            sweep_confirmed = True
            sweep_explanation = "Bullish liquidity sweep confirmed"
            break
        elif side == "SELL" and sweep.type == "BEARISH_SWEEP":
            sweep_confirmed = True
            sweep_explanation = "Bearish liquidity sweep confirmed"
            break

    # Score
    score = 0.0
    if fvg_aligned:
        score += 0.35
    if ob_nearby:
        score += 0.35
    if sweep_confirmed:
        score += 0.30

    explanations = [e for e in [fvg_explanation, ob_explanation, sweep_explanation] if e]
    explanation = " | ".join(explanations) if explanations else "No SMC confluence"

    return SignalConfluence(
        fvg_aligned=fvg_aligned,
        ob_nearby=ob_nearby,
        liquidity_sweep_confirmed=sweep_confirmed,
        smc_score=score,
        explanation=explanation,
    )

def generate_signals_v2(
    df: pd.DataFrame,
    config: StrategyConfig,
    use_smc: bool = True,
    min_smc_score: float = 0.0,
) -> pd.DataFrame:
    """
    Generate trading signals with optional Smart Money Concepts confluence.

    Same as generate_signals but adds SMC analysis and scoring.
    """
    if df.empty:
        raise ValueError("DataFrame is empty")

    if len(df) < 220:
        raise ValueError("Not enough data to warm up indicators (need at least 220 rows)")

    result = add_all_core_indicators(df.copy())

    result["signal"] = "NO_TRADE"
    result["entry"] = float("nan")
    result["stop_loss"] = float("nan")
    result["take_profit"] = float("nan")
    result["risk_reward"] = float("nan")
    result["signal_reason"] = ""
    result["smc_score"] = 0.0
    result["smc_confluence"] = ""

    for i in range(len(result)):
        row = result.iloc[i]

        trend_bias = get_trend_bias(row)

        if trend_bias == "NO_TRADE":
            result.at[result.index[i], "signal_reason"] = build_reason(
                "NO_TRADE", trend_bias, False, False, None,
            )
            continue

        adx_ok = is_adx_ok(row, min_adx=config.min_adx)
        rsi_ok = is_rsi_ok_for_side(row, trend_bias, config)

        if not adx_ok or not rsi_ok:
            result.at[result.index[i], "signal_reason"] = build_reason(
                "NO_TRADE", trend_bias, adx_ok, rsi_ok, None,
            )
            continue

        entry, stop_loss, take_profit, risk_reward = calculate_trade_levels(
            row, trend_bias, config,
        )

        if risk_reward < config.min_risk_reward:
            result.at[result.index[i], "signal_reason"] = build_reason(
                "NO_TRADE", trend_bias, adx_ok, rsi_ok, risk_reward,
            )
            continue

        # SMC confluence check
        smc_score = 0.0
        smc_explanation = ""
        if use_smc and i >= 20:
            smc = check_smc_confluence(
                df=result.iloc[:i+1],
                side=trend_bias,
                current_price=float(row["Close"]),
            )
            smc_score = smc.smc_score
            smc_explanation = smc.explanation

            if smc_score < min_smc_score:
                result.at[result.index[i], "signal"] = "NO_TRADE"
                result.at[result.index[i], "signal_reason"] = f"SMC score too low ({smc_score:.2f} < {min_smc_score}) | {build_reason('NO_TRADE', trend_bias, adx_ok, rsi_ok, risk_reward)}"
                result.at[result.index[i], "smc_score"] = smc_score
                result.at[result.index[i], "smc_confluence"] = smc_explanation
                continue

        result.at[result.index[i], "signal"] = trend_bias
        result.at[result.index[i], "entry"] = entry
        result.at[result.index[i], "stop_loss"] = stop_loss
        result.at[result.index[i], "take_profit"] = take_profit
        result.at[result.index[i], "risk_reward"] = risk_reward
        result.at[result.index[i], "signal_reason"] = build_reason(
            trend_bias, trend_bias, adx_ok, rsi_ok, risk_reward,
        )
        result.at[result.index[i], "smc_score"] = smc_score
        result.at[result.index[i], "smc_confluence"] = smc_explanation

    return result

def get_last_signal_v2(df: pd.DataFrame, config: StrategyConfig, use_smc: bool = True) -> dict:
    """Get the last valid signal with SMC info."""
    signals_df = generate_signals_v2(df, config, use_smc=use_smc)
    last_row = signals_df.iloc[-1]
    signal = last_row["signal"]

    return {
        "timestamp": str(signals_df.index[-1]),
        "signal": signal,
        "entry": float(last_row["entry"]) if pd.notna(last_row["entry"]) else None,
        "stop_loss": float(last_row["stop_loss"]) if pd.notna(last_row["stop_loss"]) else None,
        "take_profit": float(last_row["take_profit"]) if pd.notna(last_row["take_profit"]) else None,
        "risk_reward": float(last_row["risk_reward"]) if pd.notna(last_row["risk_reward"]) else None,
        "reason": str(last_row["signal_reason"]),
        "smc_score": float(last_row["smc_score"]) if pd.notna(last_row["smc_score"]) else 0.0,
        "smc_confluence": str(last_row["smc_confluence"]),
    }
