"""
Strategy Lab v5: feature-filtered MTF momentum pullback.

This experimental research strategy uses strategy_v3 as its signal base, then
applies static filters informed by Trade Outcome Analyzer observations.
It does not optimize parameters and does not execute trades.
"""

from __future__ import annotations

import pandas as pd

from src.strategy.rules import StrategyConfig
from src.strategy.signals import TradingSignal
from src.strategy_lab.strategy_v3 import generate_signal as generate_base_signal


STRATEGY_NAME = "mtf_feature_filtered_strategy"
ADX_MODERATE_MIN = 18.0
ADX_MODERATE_MAX = 25.0
REQUIRED_FEATURE_COLUMNS = {"trend_regime", "candle_regime", "adx"}


def generate_signal(df: pd.DataFrame, config: StrategyConfig | None = None) -> TradingSignal:
    """
    Generate an MTF momentum pullback signal filtered by entry-time features.

    Filters:
    - block neutral trend regime
    - accept only normal candle regime
    - accept only moderate ADX equivalent: 18 < ADX <= 25
    """
    if config is None:
        config = StrategyConfig()

    if df.empty:
        raise ValueError("DataFrame cannot be empty")

    base_signal = generate_base_signal(df, config)

    if base_signal.side not in {"BUY", "SELL"}:
        return base_signal

    latest_features = _get_latest_features(df)

    trend_regime = str(latest_features.get("trend_regime", "neutral"))
    candle_regime = str(latest_features.get("candle_regime", "normal"))
    adx = latest_features.get("adx")

    if trend_regime == "neutral":
        return _blocked_signal(
            base_signal,
            "Feature filter blocked neutral trend regime",
        )

    if candle_regime != "normal":
        return _blocked_signal(
            base_signal,
            f"Feature filter blocked candle regime={candle_regime}",
        )

    if pd.isna(adx) or not (ADX_MODERATE_MIN < float(adx) <= ADX_MODERATE_MAX):
        return _blocked_signal(
            base_signal,
            f"Feature filter blocked ADX outside moderate bucket | ADX={_format_optional_float(adx)}",
        )

    return TradingSignal(
        timestamp=base_signal.timestamp,
        symbol=base_signal.symbol,
        timeframe=base_signal.timeframe,
        side=base_signal.side,
        entry_price=base_signal.entry_price,
        stop_loss=base_signal.stop_loss,
        take_profit=base_signal.take_profit,
        risk_reward=base_signal.risk_reward,
        confidence=min(base_signal.confidence + 5.0, 100.0),
        reason=(
            f"{base_signal.reason}"
            " | Feature filtered"
            f" | trend_regime={trend_regime}"
            f" | candle_regime={candle_regime}"
            f" | ADX={float(adx):.2f}"
        ),
    )


def _get_latest_features(df):
    """
    Fast latest-feature extraction for strategy_v5.

    This function is called thousands of times during backtests.
    Do not call build_features(df) here.
    """
    if df is None or df.empty:
        return {
            "trend_regime": "neutral",
            "candle_regime": "unknown",
            "adx_bucket": "unknown",
            "adx": None,
            "rsi": None,
            "atr": None,
            "body_to_range_ratio": 0.0,
        }

    latest = df.iloc[-1]

    precomputed_trend_regime = latest.get("trend_regime", None)
    precomputed_candle_regime = latest.get("candle_regime", None)
    precomputed_adx_bucket = latest.get("adx_bucket", None)

    close = float(latest.get("Close", latest.get("close", 0.0)))
    open_price = float(latest.get("Open", latest.get("open", close)))
    high = float(latest.get("High", latest.get("high", close)))
    low = float(latest.get("Low", latest.get("low", close)))

    candle_range = max(high - low, 1e-9)
    candle_body = abs(close - open_price)
    body_to_range_ratio = candle_body / candle_range

    ema20 = latest.get("ema_20", latest.get("EMA_20", None))
    ema50 = latest.get("ema_50", latest.get("EMA_50", None))
    ema200 = latest.get("ema_200", latest.get("EMA_200", None))
    adx = latest.get("adx", latest.get("ADX_14", latest.get("ADX", None)))
    rsi = latest.get("rsi", latest.get("RSI_14", latest.get("RSI", None)))
    atr = latest.get("atr", latest.get("ATR_14", latest.get("ATR", None)))

    if ema20 is None and len(df) >= 20:
        ema20 = df["Close"].tail(20).ewm(span=20, adjust=False).mean().iloc[-1]

    if ema50 is None and len(df) >= 50:
        ema50 = df["Close"].tail(50).ewm(span=50, adjust=False).mean().iloc[-1]

    if ema200 is None and len(df) >= 200:
        ema200 = df["Close"].tail(200).ewm(span=200, adjust=False).mean().iloc[-1]

    trend_regime = precomputed_trend_regime if precomputed_trend_regime is not None else "neutral"
    if precomputed_trend_regime is None and ema20 is not None and ema50 is not None and ema200 is not None:
        ema20_value = float(ema20)
        ema50_value = float(ema50)
        ema200_value = float(ema200)

        if close > ema20_value > ema50_value > ema200_value:
            trend_regime = "bullish"
        elif close < ema20_value < ema50_value < ema200_value:
            trend_regime = "bearish"

    if precomputed_candle_regime is not None:
        candle_regime = precomputed_candle_regime
    elif body_to_range_ratio >= 0.70:
        candle_regime = "impulse"
    elif body_to_range_ratio <= 0.25:
        candle_regime = "indecision"
    else:
        candle_regime = "normal"

    adx_bucket = precomputed_adx_bucket if precomputed_adx_bucket is not None else "unknown"
    if precomputed_adx_bucket is None and adx is not None:
        adx_value = float(adx)
        if adx_value < 18:
            adx_bucket = "weak"
        elif adx_value < 25:
            adx_bucket = "moderate"
        elif adx_value < 35:
            adx_bucket = "strong"
        else:
            adx_bucket = "very_strong"

    return {
        "trend_regime": trend_regime,
        "candle_regime": candle_regime,
        "adx_bucket": adx_bucket,
        "adx": float(adx) if adx is not None else None,
        "rsi": float(rsi) if rsi is not None else None,
        "atr": float(atr) if atr is not None else None,
        "body_to_range_ratio": body_to_range_ratio,
    }


def _blocked_signal(base_signal: TradingSignal, reason: str) -> TradingSignal:
    """Convert a tradable base signal into a blocked NO_TRADE signal."""
    return TradingSignal(
        timestamp=base_signal.timestamp,
        symbol=base_signal.symbol,
        timeframe=base_signal.timeframe,
        side="NO_TRADE",
        entry_price=base_signal.entry_price,
        stop_loss=base_signal.stop_loss,
        take_profit=base_signal.take_profit,
        risk_reward=base_signal.risk_reward,
        confidence=0.0,
        reason=f"{reason} | Base side={base_signal.side}",
    )


def _format_optional_float(value) -> str:
    """Format a float-like value while preserving NaN readability."""
    if pd.isna(value):
        return "nan"

    return f"{float(value):.2f}"
