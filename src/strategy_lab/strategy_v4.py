"""
Strategy Lab v4: strict Off Session MTF momentum pullback.

This is a more selective research-only variant of strategy_v3. It keeps the
placeholder MTF idea simple, but adds static quality filters to reduce low
quality setups without optimizing parameters.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from src.analysis.session_analysis import classify_hour_to_session
from src.strategy.rules import SignalSide, StrategyConfig, calculate_trade_levels, is_rsi_ok_for_side
from src.strategy.signals import TradingSignal
from src.strategy.structure import summarize_market_structure


STRATEGY_NAME = "mtf_strict_offsession_strategy"
REQUIRED_RISK_PER_TRADE = 0.0025
REQUIRED_MIN_RISK_REWARD = 2.0
REQUIRED_ALLOWED_SESSIONS = ["Off Session"]

MOMENTUM_LOOKBACK = 5
MIN_ADX = 22.0
MAX_EXTENSION_ATR = 0.9
MAX_BODY_ATR = 0.8
MAX_RANGE_ATR = 1.6


def generate_signal(df: pd.DataFrame, config: StrategyConfig | None = None) -> TradingSignal:
    """
    Generate a strict Off Session momentum-pullback signal.

    Requirements:
    - latest candle must be Off Session
    - EMA 20/50/200 directional bias must align
    - ADX and DI momentum must be clear
    - pullback must reclaim/reject EMA 20
    - entry must not be too extended from EMA 20
    - latest candle must not be too impulsive versus ATR
    - available market structure must not conflict with the signal
    """
    if config is None:
        config = StrategyConfig()

    if df.empty:
        raise ValueError("DataFrame cannot be empty")

    required_columns = [
        "Open",
        "High",
        "Low",
        "Close",
        "EMA_20",
        "EMA_50",
        "EMA_200",
        "RSI_14",
        "ATR_14",
        "ADX_14",
        "PLUS_DI_14",
        "MINUS_DI_14",
    ]
    missing = [column for column in required_columns if column not in df.columns]

    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    timestamp = _get_timestamp(df)
    session_name = classify_hour_to_session(timestamp.hour)

    if session_name != "Off Session":
        return _no_trade(timestamp, config, f"Strict MTF only trades Off Session | Session={session_name}")

    if len(df) <= MOMENTUM_LOOKBACK:
        return _no_trade(timestamp, config, "Not enough candles for strict momentum proxy")

    latest = df.iloc[-1]
    previous = df.iloc[-2]
    lookback = df.iloc[-(MOMENTUM_LOOKBACK + 1)]

    side = _detect_strict_side(latest, previous, lookback)

    if side == "NO_TRADE":
        return _no_trade(timestamp, config, "No clear strict momentum pullback setup")

    if not _has_clear_momentum(latest, side, config):
        return _no_trade(timestamp, config, f"Strict momentum filter blocked | Side={side}")

    if _is_too_extended(latest):
        return _no_trade(timestamp, config, f"Entry too extended from EMA 20 | Side={side}")

    if _is_impulsive_candle(latest):
        return _no_trade(timestamp, config, f"Latest candle too impulsive versus ATR | Side={side}")

    if _structure_conflicts(df, side):
        return _no_trade(timestamp, config, f"Market structure conflicts with strict signal | Side={side}")

    entry, stop_loss, take_profit, risk_reward = calculate_trade_levels(latest, side, config)
    required_rr = max(config.min_risk_reward, REQUIRED_MIN_RISK_REWARD)

    if risk_reward < required_rr:
        return _no_trade(
            timestamp,
            config,
            f"Strict MTF RR below minimum | RR={risk_reward:.2f}",
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
        confidence=82.0,
        reason=(
            "Strict Off Session MTF momentum pullback"
            f" | Side={side}"
            f" | Session={session_name}"
            f" | ADX={float(latest['ADX_14']):.2f}"
            f" | RR={risk_reward:.2f}"
        ),
    )


def _detect_strict_side(latest: pd.Series, previous: pd.Series, lookback: pd.Series) -> SignalSide:
    """Detect a strict directional momentum-pullback side."""
    close = float(latest["Close"])
    previous_close = float(previous["Close"])
    lookback_close = float(lookback["Close"])

    ema_20 = float(latest["EMA_20"])
    ema_50 = float(latest["EMA_50"])
    ema_200 = float(latest["EMA_200"])
    previous_ema_20 = float(previous["EMA_20"])
    lookback_ema_20 = float(lookback["EMA_20"])
    lookback_ema_50 = float(lookback["EMA_50"])

    buy_bias = ema_20 > ema_50 > ema_200 and close > ema_20
    buy_momentum = close > lookback_close and ema_20 > lookback_ema_20 and ema_50 >= lookback_ema_50
    buy_pullback = previous_close <= previous_ema_20 and close > ema_20

    if buy_bias and buy_momentum and buy_pullback:
        return "BUY"

    sell_bias = ema_20 < ema_50 < ema_200 and close < ema_20
    sell_momentum = close < lookback_close and ema_20 < lookback_ema_20 and ema_50 <= lookback_ema_50
    sell_pullback = previous_close >= previous_ema_20 and close < ema_20

    if sell_bias and sell_momentum and sell_pullback:
        return "SELL"

    return "NO_TRADE"


def _has_clear_momentum(latest: pd.Series, side: SignalSide, config: StrategyConfig) -> bool:
    """Validate ADX, directional DI, and RSI filters."""
    adx = latest["ADX_14"]

    if pd.isna(adx) or float(adx) < max(config.min_adx, MIN_ADX):
        return False

    plus_di = latest["PLUS_DI_14"]
    minus_di = latest["MINUS_DI_14"]

    if pd.isna(plus_di) or pd.isna(minus_di):
        return False

    if side == "BUY" and float(plus_di) <= float(minus_di):
        return False

    if side == "SELL" and float(minus_di) <= float(plus_di):
        return False

    return is_rsi_ok_for_side(latest, side, config)


def _is_too_extended(latest: pd.Series) -> bool:
    """Avoid entries too far from EMA 20 relative to ATR."""
    atr = latest["ATR_14"]

    if pd.isna(atr) or float(atr) <= 0:
        return True

    extension = abs(float(latest["Close"]) - float(latest["EMA_20"]))
    return extension > float(atr) * MAX_EXTENSION_ATR


def _is_impulsive_candle(latest: pd.Series) -> bool:
    """Avoid entries after an already oversized candle."""
    atr = latest["ATR_14"]

    if pd.isna(atr) or float(atr) <= 0:
        return True

    body = abs(float(latest["Close"]) - float(latest["Open"]))
    candle_range = float(latest["High"]) - float(latest["Low"])

    return body > float(atr) * MAX_BODY_ATR or candle_range > float(atr) * MAX_RANGE_ATR


def _structure_conflicts(df: pd.DataFrame, side: SignalSide) -> bool:
    """Use existing structure helper only when it has a clear opposing view."""
    summary = summarize_market_structure(df, lookback=2)

    if side == "BUY":
        return summary.trend == "BEARISH" or summary.event == "BOS_BEARISH"

    if side == "SELL":
        return summary.trend == "BULLISH" or summary.event == "BOS_BULLISH"

    return True


def _no_trade(
    timestamp: datetime,
    config: StrategyConfig,
    reason: str,
    entry_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    risk_reward: float | None = None,
) -> TradingSignal:
    """Build a NO_TRADE signal for the strict strategy."""
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
