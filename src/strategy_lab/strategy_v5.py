"""
Strategy Lab v5: feature-filtered MTF momentum pullback.

This experimental research strategy uses strategy_v3 as its signal base, then
applies static filters informed by Trade Outcome Analyzer observations.
It does not optimize parameters and does not execute trades.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategy.rules import StrategyConfig
from src.strategy.signals import TradingSignal
from src.strategy_lab.strategy_v3 import generate_signal as generate_base_signal


STRATEGY_NAME = "mtf_feature_filtered_strategy"
ADX_MODERATE_MIN = 18.0
ADX_MODERATE_MAX = 25.0
REQUIRED_HISTORY_CANDLES = 500
REQUIRED_FEATURE_COLUMNS = {"trend_regime", "candle_regime", "adx"}


@dataclass(frozen=True)
class FeatureFilterConfig:
    """Configurable research filters for strategy_v5."""

    allowed_trend_regimes: tuple[str, ...] = ("bullish", "bearish")
    allowed_candle_regimes: tuple[str, ...] = ("normal",)
    allowed_adx_buckets: tuple[str, ...] = ("moderate",)


DEFAULT_FEATURE_FILTER_CONFIG = FeatureFilterConfig()


def generate_signal(df: pd.DataFrame, config: StrategyConfig | None = None) -> TradingSignal:
    """Generate the default feature-filtered MTF momentum pullback signal."""
    return generate_signal_with_filters(df, config, DEFAULT_FEATURE_FILTER_CONFIG)


def generate_signal_with_filters(
    df: pd.DataFrame,
    config: StrategyConfig | None = None,
    feature_filter_config: FeatureFilterConfig = DEFAULT_FEATURE_FILTER_CONFIG,
) -> TradingSignal:
    """
    Generate an MTF momentum pullback signal filtered by entry-time features.

    Filters:
    - allowed trend regimes
    - allowed candle regimes
    - allowed ADX buckets
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
    adx_bucket = str(latest_features.get("adx_bucket", "unknown"))
    adx = latest_features.get("adx")

    if trend_regime not in feature_filter_config.allowed_trend_regimes:
        reason = (
            "Feature filter blocked neutral trend regime"
            if trend_regime == "neutral"
            else f"Feature filter blocked trend regime={trend_regime}"
        )
        return _blocked_signal(
            base_signal,
            reason,
        )

    if candle_regime not in feature_filter_config.allowed_candle_regimes:
        return _blocked_signal(
            base_signal,
            f"Feature filter blocked candle regime={candle_regime}",
        )

    if pd.isna(adx) or adx_bucket not in feature_filter_config.allowed_adx_buckets:
        return _blocked_signal(
            base_signal,
            f"Feature filter blocked ADX bucket={adx_bucket} | ADX={_format_optional_float(adx)}",
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
            f" | adx_bucket={adx_bucket}"
            f" | ADX={float(adx):.2f}"
        ),
    )


def make_signal_generator(feature_filter_config: FeatureFilterConfig):
    """Build a signal generator function for a specific feature filter set."""

    def _generate_signal(df: pd.DataFrame, config: StrategyConfig | None = None) -> TradingSignal:
        return generate_signal_with_filters(df, config, feature_filter_config)

    _generate_signal.required_history_candles = REQUIRED_HISTORY_CANDLES
    return _generate_signal


def _get_latest_features(df):
    """
    Fast latest-feature extraction for strategy_v5.

    This function is called thousands of times during backtests.
    Keep fallback calculations local and lightweight.
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

    if REQUIRED_FEATURE_COLUMNS.issubset(df.columns):
        trend_regime = latest.get("trend_regime", "neutral")
        candle_regime = latest.get("candle_regime", "normal")
        adx = latest.get("adx", None)
        adx_bucket = latest.get("adx_bucket", None)
        if adx_bucket is None or pd.isna(adx_bucket):
            adx_bucket = _classify_adx_bucket(adx)

        return {
            "trend_regime": "neutral" if pd.isna(trend_regime) else str(trend_regime),
            "candle_regime": "normal" if pd.isna(candle_regime) else str(candle_regime),
            "adx_bucket": str(adx_bucket),
            "adx": float(adx) if adx is not None and not pd.isna(adx) else None,
            "rsi": _optional_float(latest.get("rsi", None)),
            "atr": _optional_float(latest.get("atr", None)),
            "body_to_range_ratio": _optional_float(latest.get("body_to_range_ratio", 0.0)),
        }

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
        adx_bucket = _classify_adx_bucket(adx)

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


def _classify_adx_bucket(adx) -> str:
    """Classify ADX into the buckets used by outcome analysis."""
    if adx is None or pd.isna(adx):
        return "unknown"

    adx_value = float(adx)
    if adx_value <= ADX_MODERATE_MIN:
        return "weak"
    if adx_value <= ADX_MODERATE_MAX:
        return "moderate"
    if adx_value < 35:
        return "strong"
    return "very_strong"


def _optional_float(value) -> float | None:
    """Convert optional numeric values while preserving missing values."""
    if value is None or pd.isna(value):
        return None

    return float(value)


generate_signal.required_history_candles = REQUIRED_HISTORY_CANDLES
generate_signal_with_filters.required_history_candles = REQUIRED_HISTORY_CANDLES
