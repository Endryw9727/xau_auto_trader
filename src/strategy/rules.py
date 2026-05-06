"""
Strategy rules for XAU/USD.

This module contains simple and testable rule functions.
The rules do not execute trades. They only help decide if a setup is valid.

First version logic:
- trend filter with EMA 20 / EMA 50
- ADX trend strength filter
- RSI extreme filter
- ATR-based stop loss
- minimum risk/reward filter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


SignalSide = Literal["BUY", "SELL", "NO_TRADE"]


@dataclass(frozen=True)
class StrategyConfig:
    """Strategy configuration."""

    symbol: str = "XAUUSD"
    timeframe: str = "15m"
    min_adx: float = 18.0
    min_risk_reward: float = 2.0
    atr_multiplier_sl: float = 1.5
    atr_multiplier_tp: float = 3.0
    rsi_buy_max: float = 70.0
    rsi_sell_min: float = 30.0


def get_trend_bias(row: pd.Series) -> SignalSide:
    """
    Detect directional bias using EMA 20 and EMA 50.

    BUY bias:
    - EMA_20 > EMA_50
    - Close > EMA_20

    SELL bias:
    - EMA_20 < EMA_50
    - Close < EMA_20
    """
    required = ["Close", "EMA_20", "EMA_50"]
    _validate_row_columns(row, required)

    close = float(row["Close"])
    ema_20 = float(row["EMA_20"])
    ema_50 = float(row["EMA_50"])

    if ema_20 > ema_50 and close > ema_20:
        return "BUY"

    if ema_20 < ema_50 and close < ema_20:
        return "SELL"

    return "NO_TRADE"


def is_adx_ok(row: pd.Series, min_adx: float = 18.0) -> bool:
    """Return True if ADX confirms enough trend strength."""
    _validate_row_columns(row, ["ADX_14"])

    adx = row["ADX_14"]

    if pd.isna(adx):
        return False

    return float(adx) >= min_adx


def is_rsi_ok_for_side(row: pd.Series, side: SignalSide, config: StrategyConfig) -> bool:
    """
    RSI filter.

    For BUY:
    - avoid buying when RSI is too high.

    For SELL:
    - avoid selling when RSI is too low.
    """
    _validate_row_columns(row, ["RSI_14"])

    rsi = row["RSI_14"]

    if pd.isna(rsi):
        return False

    rsi_value = float(rsi)

    if side == "BUY":
        return rsi_value <= config.rsi_buy_max

    if side == "SELL":
        return rsi_value >= config.rsi_sell_min

    return False


def calculate_trade_levels(row: pd.Series, side: SignalSide, config: StrategyConfig) -> tuple[float, float, float, float]:
    """
    Calculate entry, stop loss, take profit and risk/reward.

    Uses ATR for distance:
    - stop distance = ATR * atr_multiplier_sl
    - target distance = ATR * atr_multiplier_tp
    """
    _validate_row_columns(row, ["Close", "ATR_14"])

    if side not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")

    close = float(row["Close"])
    atr = row["ATR_14"]

    if pd.isna(atr) or float(atr) <= 0:
        raise ValueError("ATR must be available and greater than 0")

    atr_value = float(atr)
    stop_distance = atr_value * config.atr_multiplier_sl
    target_distance = atr_value * config.atr_multiplier_tp

    if side == "BUY":
        entry = close
        stop_loss = entry - stop_distance
        take_profit = entry + target_distance
    else:
        entry = close
        stop_loss = entry + stop_distance
        take_profit = entry - target_distance

    risk = abs(entry - stop_loss)
    reward = abs(take_profit - entry)
    risk_reward = reward / risk if risk > 0 else 0.0

    return entry, stop_loss, take_profit, risk_reward


def build_reason(
    side: SignalSide,
    trend_bias: SignalSide,
    adx_ok: bool,
    rsi_ok: bool,
    risk_reward: float | None,
) -> str:
    """Build a human-readable reason for the signal decision."""
    parts = [
        f"Side={side}",
        f"Trend bias={trend_bias}",
        f"ADX ok={adx_ok}",
        f"RSI ok={rsi_ok}",
    ]

    if risk_reward is not None:
        parts.append(f"RR={risk_reward:.2f}")

    return " | ".join(parts)


def _validate_row_columns(row: pd.Series, required_columns: list[str]) -> None:
    """Validate that a pandas Series contains required columns."""
    missing = [column for column in required_columns if column not in row.index]

    if missing:
        raise ValueError(f"Missing required columns: {missing}")
