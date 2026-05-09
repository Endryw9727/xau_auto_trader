"""
Strategy Lab v3: MTF momentum pullback placeholder.

This is deliberately simple and testable. It does not optimize parameters and
does not claim profitability. The "MTF" idea is represented by a conservative
higher-window momentum proxy until real multi-timeframe data is introduced.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from src.strategy.rules import (
    SignalSide,
    StrategyConfig,
    calculate_trade_levels,
    is_adx_ok,
    is_rsi_ok_for_side,
)
from src.strategy.signals import TradingSignal


STRATEGY_NAME = "mtf_momentum_pullback_strategy"
MOMENTUM_LOOKBACK = 3


def generate_signal(df: pd.DataFrame, config: StrategyConfig | None = None) -> TradingSignal:
    """
    Generate a placeholder momentum-pullback signal.

    BUY requires:
    - EMA_20 above EMA_50
    - latest close above the close from MOMENTUM_LOOKBACK candles ago
    - previous candle pulled back to/below EMA_20
    - latest candle reclaimed EMA_20

    SELL mirrors the same logic.
    """
    if config is None:
        config = StrategyConfig()

    if df.empty:
        raise ValueError("DataFrame cannot be empty")

    required_columns = ["Close", "EMA_20", "EMA_50", "RSI_14", "ATR_14", "ADX_14"]
    missing = [column for column in required_columns if column not in df.columns]

    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    timestamp = _get_timestamp(df)

    if len(df) <= MOMENTUM_LOOKBACK:
        return _no_trade(timestamp, config, "Not enough candles for momentum proxy")

    latest = df.iloc[-1]
    previous = df.iloc[-2]
    lookback = df.iloc[-(MOMENTUM_LOOKBACK + 1)]

    close = float(latest["Close"])
    previous_close = float(previous["Close"])
    lookback_close = float(lookback["Close"])
    ema_20 = float(latest["EMA_20"])
    ema_50 = float(latest["EMA_50"])
    previous_ema_20 = float(previous["EMA_20"])

    side = _detect_placeholder_side(
        close=close,
        previous_close=previous_close,
        lookback_close=lookback_close,
        ema_20=ema_20,
        ema_50=ema_50,
        previous_ema_20=previous_ema_20,
    )

    if side == "NO_TRADE":
        return _no_trade(timestamp, config, "No momentum pullback setup")

    adx_ok = is_adx_ok(latest, min_adx=config.min_adx)
    rsi_ok = is_rsi_ok_for_side(latest, side, config)

    if not adx_ok or not rsi_ok:
        return _no_trade(
            timestamp,
            config,
            f"Momentum pullback blocked | ADX ok={adx_ok} | RSI ok={rsi_ok}",
        )

    entry, stop_loss, take_profit, risk_reward = calculate_trade_levels(latest, side, config)

    if risk_reward < config.min_risk_reward:
        return _no_trade(
            timestamp,
            config,
            f"Momentum pullback RR below minimum | RR={risk_reward:.2f}",
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
        )

    return TradingSignal(
        timestamp=timestamp,
        symbol=config.symbol,
        timeframe=config.timeframe,
        side=side,
        entry_price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=risk_reward,
        confidence=70.0,
        reason=(
            "MTF momentum pullback placeholder"
            f" | Side={side}"
            f" | ADX ok={adx_ok}"
            f" | RSI ok={rsi_ok}"
            f" | RR={risk_reward:.2f}"
        ),
    )


def _detect_placeholder_side(
    close: float,
    previous_close: float,
    lookback_close: float,
    ema_20: float,
    ema_50: float,
    previous_ema_20: float,
) -> SignalSide:
    """Detect a simple momentum-pullback side."""
    buy_momentum = ema_20 > ema_50 and close > lookback_close
    buy_pullback = previous_close <= previous_ema_20 and close > ema_20

    if buy_momentum and buy_pullback:
        return "BUY"

    sell_momentum = ema_20 < ema_50 and close < lookback_close
    sell_pullback = previous_close >= previous_ema_20 and close < ema_20

    if sell_momentum and sell_pullback:
        return "SELL"

    return "NO_TRADE"


def _no_trade(
    timestamp: datetime,
    config: StrategyConfig,
    reason: str,
    entry_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    risk_reward: float | None = None,
) -> TradingSignal:
    """Build a NO_TRADE signal for this placeholder strategy."""
    return TradingSignal(
        timestamp=timestamp,
        symbol=config.symbol,
        timeframe=config.timeframe,
        side="NO_TRADE",
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=risk_reward,
        confidence=0.0,
        reason=reason,
    )


def _get_timestamp(df: pd.DataFrame) -> datetime:
    """Return the latest index timestamp if available."""
    latest_index = df.index[-1]

    if isinstance(latest_index, pd.Timestamp):
        return latest_index.to_pydatetime()

    return datetime.now(UTC)
