"""
Signal generation logic for XAU/USD.

This module:
1. adds technical indicators to market data
2. generates BUY / SELL / NO_TRADE signals
3. calculates stop loss and take profit levels
4. builds human-readable reasons for each signal

Signals are not orders. They are just candidate trade ideas.
"""

from __future__ import annotations

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

SignalSide = Literal["BUY", "SELL", "NO_TRADE"]

def generate_signals(df: pd.DataFrame, config: StrategyConfig) -> pd.DataFrame:
    """
    Generate a DataFrame of trading signals.

    For each row with enough indicator data, the function evaluates:
    - trend bias from EMA 20 / EMA 50
    - ADX trend strength
    - RSI extreme filter
    - risk/reward ratio

    Output columns added to the DataFrame:
    - signal: BUY, SELL, or NO_TRADE
    - entry, stop_loss, take_profit: trade levels
    - risk_reward: calculated ratio
    - signal_reason: human-readable explanation
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

    for i in range(len(result)):
        row = result.iloc[i]

        trend_bias = get_trend_bias(row)

        if trend_bias == "NO_TRADE":
            result.at[result.index[i], "signal_reason"] = build_reason(
                "NO_TRADE",
                trend_bias,
                False,
                False,
                None,
            )
            continue

        adx_ok = is_adx_ok(row, min_adx=config.min_adx)
        rsi_ok = is_rsi_ok_for_side(row, trend_bias, config)

        if not adx_ok or not rsi_ok:
            result.at[result.index[i], "signal_reason"] = build_reason(
                "NO_TRADE",
                trend_bias,
                adx_ok,
                rsi_ok,
                None,
            )
            continue

        entry, stop_loss, take_profit, risk_reward = calculate_trade_levels(
            row,
            trend_bias,
            config,
        )

        if risk_reward < config.min_risk_reward:
            result.at[result.index[i], "signal_reason"] = build_reason(
                "NO_TRADE",
                trend_bias,
                adx_ok,
                rsi_ok,
                risk_reward,
            )
            continue

        result.at[result.index[i], "signal"] = trend_bias
        result.at[result.index[i], "entry"] = entry
        result.at[result.index[i], "stop_loss"] = stop_loss
        result.at[result.index[i], "take_profit"] = take_profit
        result.at[result.index[i], "risk_reward"] = risk_reward
        result.at[result.index[i], "signal_reason"] = build_reason(
            trend_bias,
            trend_bias,
            adx_ok,
            rsi_ok,
            risk_reward,
        )

    return result

def get_last_signal(df: pd.DataFrame, config: StrategyConfig) -> dict:
    """
    Get the last valid signal from a DataFrame.

    Returns a dictionary with signal details.
    """
    signals_df = generate_signals(df, config)

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
    }
