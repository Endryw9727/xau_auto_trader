"""
Signal generation module.

This module creates BUY / SELL / NO_TRADE signals.
It does not execute trades.

A signal is only an analytical output. Execution will be handled later by:
- risk manager
- paper broker
- future protected live broker
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import pandas as pd

from src.strategy.rules import (
    SignalSide,
    StrategyConfig,
    build_reason,
    calculate_trade_levels,
    get_trend_bias,
    is_adx_ok,
    is_rsi_ok_for_side,
)


@dataclass(frozen=True)
class TradingSignal:
    """Structured trading signal."""

    timestamp: datetime
    symbol: str
    timeframe: str
    side: SignalSide

    entry_price: float | None
    stop_loss: float | None
    take_profit: float | None

    risk_reward: float | None
    confidence: float
    reason: str


def generate_signal(df: pd.DataFrame, config: StrategyConfig | None = None) -> TradingSignal:
    """
    Generate a trading signal from the latest candle.

    Returns:
    - BUY
    - SELL
    - NO_TRADE

    Required columns:
    Close, EMA_20, EMA_50, RSI_14, ATR_14, ADX_14
    """
    if config is None:
        config = StrategyConfig()

    if df.empty:
        raise ValueError("DataFrame cannot be empty")

    latest = df.iloc[-1]
    timestamp = _get_timestamp(df)

    trend_bias = get_trend_bias(latest)

    if trend_bias == "NO_TRADE":
        reason = build_reason(
            side="NO_TRADE",
            trend_bias=trend_bias,
            adx_ok=False,
            rsi_ok=False,
            risk_reward=None,
        )

        return TradingSignal(
            timestamp=timestamp,
            symbol=config.symbol,
            timeframe=config.timeframe,
            side="NO_TRADE",
            entry_price=None,
            stop_loss=None,
            take_profit=None,
            risk_reward=None,
            confidence=0.0,
            reason=reason,
        )

    adx_ok = is_adx_ok(latest, min_adx=config.min_adx)
    rsi_ok = is_rsi_ok_for_side(latest, trend_bias, config)

    if not adx_ok or not rsi_ok:
        confidence = _calculate_confidence(trend_bias, adx_ok, rsi_ok, risk_reward=None)
        reason = build_reason(
            side="NO_TRADE",
            trend_bias=trend_bias,
            adx_ok=adx_ok,
            rsi_ok=rsi_ok,
            risk_reward=None,
        )

        return TradingSignal(
            timestamp=timestamp,
            symbol=config.symbol,
            timeframe=config.timeframe,
            side="NO_TRADE",
            entry_price=None,
            stop_loss=None,
            take_profit=None,
            risk_reward=None,
            confidence=confidence,
            reason=reason,
        )

    entry, stop_loss, take_profit, risk_reward = calculate_trade_levels(latest, trend_bias, config)

    if risk_reward < config.min_risk_reward:
        confidence = _calculate_confidence(trend_bias, adx_ok, rsi_ok, risk_reward)
        reason = build_reason(
            side="NO_TRADE",
            trend_bias=trend_bias,
            adx_ok=adx_ok,
            rsi_ok=rsi_ok,
            risk_reward=risk_reward,
        )

        return TradingSignal(
            timestamp=timestamp,
            symbol=config.symbol,
            timeframe=config.timeframe,
            side="NO_TRADE",
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
            confidence=confidence,
            reason=reason + " | RR below minimum",
        )

    confidence = _calculate_confidence(trend_bias, adx_ok, rsi_ok, risk_reward)
    reason = build_reason(
        side=trend_bias,
        trend_bias=trend_bias,
        adx_ok=adx_ok,
        rsi_ok=rsi_ok,
        risk_reward=risk_reward,
    )

    return TradingSignal(
        timestamp=timestamp,
        symbol=config.symbol,
        timeframe=config.timeframe,
        side=trend_bias,
        entry_price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=risk_reward,
        confidence=confidence,
        reason=reason,
    )


def signal_to_dict(signal: TradingSignal) -> dict:
    """Convert a TradingSignal dataclass to a dictionary."""
    return {
        "timestamp": signal.timestamp,
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "side": signal.side,
        "entry_price": signal.entry_price,
        "stop_loss": signal.stop_loss,
        "take_profit": signal.take_profit,
        "risk_reward": signal.risk_reward,
        "confidence": signal.confidence,
        "reason": signal.reason,
    }


def _calculate_confidence(
    side: SignalSide,
    adx_ok: bool,
    rsi_ok: bool,
    risk_reward: float | None,
) -> float:
    """
    Calculate a simple confidence score from 0 to 100.

    This is not a guarantee of profitability.
    It only summarizes how many rules were satisfied.
    """
    if side == "NO_TRADE":
        return 0.0

    score = 40.0

    if adx_ok:
        score += 20.0

    if rsi_ok:
        score += 20.0

    if risk_reward is not None:
        if risk_reward >= 3.0:
            score += 20.0
        elif risk_reward >= 2.0:
            score += 15.0
        elif risk_reward >= 1.5:
            score += 5.0

    return min(score, 100.0)


def _get_timestamp(df: pd.DataFrame) -> datetime:
    """Return latest index timestamp if DatetimeIndex exists, otherwise utcnow."""
    latest_index = df.index[-1]

    if isinstance(latest_index, pd.Timestamp):
        return latest_index.to_pydatetime()

    return datetime.now(UTC)
