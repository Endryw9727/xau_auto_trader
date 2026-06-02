"""Causal Smart Money Concepts overlay for V2 shadow reporting.

Some V2 SMC concepts require later candles for confirmation. This adapter keeps
them diagnostic-only and records `available_at` for every feature that depends
on a confirming candle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


FeatureKind = Literal["FVG", "ORDER_BLOCK", "LIQUIDITY_SWEEP"]
FeatureSide = Literal["BULLISH", "BEARISH"]


@dataclass(frozen=True)
class ShadowSMCFeature:
    """One causal shadow SMC feature."""

    kind: FeatureKind
    side: FeatureSide
    event_time: pd.Timestamp
    available_at: pd.Timestamp
    level: float | None
    top: float | None
    bottom: float | None
    note: str

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "side": self.side,
            "event_time": self.event_time.isoformat(),
            "available_at": self.available_at.isoformat(),
            "level": _round_or_none(self.level),
            "top": _round_or_none(self.top),
            "bottom": _round_or_none(self.bottom),
            "note": self.note,
        }


@dataclass(frozen=True)
class ShadowSMCReport:
    """Smart money overlay summary."""

    bias: str
    features: tuple[ShadowSMCFeature, ...]
    key_support: float | None
    key_resistance: float | None
    explanation: str

    def to_dict(self) -> dict[str, object]:
        return {
            "bias": self.bias,
            "key_support": _round_or_none(self.key_support),
            "key_resistance": _round_or_none(self.key_resistance),
            "explanation": self.explanation,
            "features": [feature.to_dict() for feature in self.features],
        }


def analyze_shadow_smc(df: pd.DataFrame, *, lookback: int = 50, as_of: pd.Timestamp | None = None) -> ShadowSMCReport:
    """Analyze causal SMC overlays up to `as_of`."""
    data = _normalize_ohlc(df)
    if data.empty:
        return ShadowSMCReport("NEUTRAL", (), None, None, "No OHLC data available for SMC overlay.")
    cutoff = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp(data.index[-1])
    visible = data[data.index <= cutoff].copy()
    if visible.empty:
        return ShadowSMCReport("NEUTRAL", (), None, None, "No candles available at requested as_of time.")

    features = []
    features.extend(detect_fvgs(visible))
    features.extend(detect_order_blocks(visible))
    features.extend(detect_liquidity_sweeps(visible))
    available = tuple(feature for feature in features if feature.available_at <= cutoff)
    recent = tuple(available[-lookback:])

    bullish = sum(1 for feature in recent if feature.side == "BULLISH")
    bearish = sum(1 for feature in recent if feature.side == "BEARISH")
    if bullish > bearish * 1.5:
        bias = "BULLISH"
    elif bearish > bullish * 1.5:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    bullish_levels = [feature.bottom for feature in recent if feature.side == "BULLISH" and feature.bottom is not None]
    bearish_levels = [feature.top for feature in recent if feature.side == "BEARISH" and feature.top is not None]
    key_support = min(bullish_levels) if bullish_levels else None
    key_resistance = max(bearish_levels) if bearish_levels else None
    explanation = (
        f"SMC shadow bias={bias}; features={len(recent)}; bullish={bullish}; bearish={bearish}; "
        "diagnostic-only, not used as a live filter."
    )
    return ShadowSMCReport(bias, recent, key_support, key_resistance, explanation)


def detect_fvgs(df: pd.DataFrame) -> tuple[ShadowSMCFeature, ...]:
    """Detect FVGs that are available at the FVG candle close."""
    data = _normalize_ohlc(df)
    features: list[ShadowSMCFeature] = []
    for i in range(2, len(data)):
        current = data.iloc[i]
        anchor = data.iloc[i - 2]
        event_time = pd.Timestamp(data.index[i])
        if current["Low"] > anchor["High"]:
            features.append(
                ShadowSMCFeature(
                    "FVG",
                    "BULLISH",
                    event_time,
                    event_time,
                    None,
                    float(current["Low"]),
                    float(anchor["High"]),
                    "Bullish FVG confirmed at current candle close.",
                )
            )
        if current["High"] < anchor["Low"]:
            features.append(
                ShadowSMCFeature(
                    "FVG",
                    "BEARISH",
                    event_time,
                    event_time,
                    None,
                    float(anchor["Low"]),
                    float(current["High"]),
                    "Bearish FVG confirmed at current candle close.",
                )
            )
    return tuple(features)


def detect_order_blocks(df: pd.DataFrame, *, lookback: int = 5) -> tuple[ShadowSMCFeature, ...]:
    """Detect order blocks and expose them only after the impulse candle."""
    data = _normalize_ohlc(df)
    features: list[ShadowSMCFeature] = []
    if len(data) < lookback + 2:
        return ()
    for i in range(lookback, len(data) - 1):
        current = data.iloc[i]
        impulse = data.iloc[i + 1]
        avg_range = (data["High"].iloc[i - lookback:i] - data["Low"].iloc[i - lookback:i]).mean()
        impulse_range = impulse["High"] - impulse["Low"]
        event_time = pd.Timestamp(data.index[i])
        available_at = pd.Timestamp(data.index[i + 1])
        if current["Close"] < current["Open"] and impulse["Close"] > impulse["Open"] and impulse_range > avg_range * 1.2:
            features.append(
                ShadowSMCFeature(
                    "ORDER_BLOCK",
                    "BULLISH",
                    event_time,
                    available_at,
                    float(current["Low"]),
                    float(current["High"]),
                    float(current["Low"]),
                    "Bullish order block; available after next-candle impulse confirmation.",
                )
            )
        if current["Close"] > current["Open"] and impulse["Close"] < impulse["Open"] and impulse_range > avg_range * 1.2:
            features.append(
                ShadowSMCFeature(
                    "ORDER_BLOCK",
                    "BEARISH",
                    event_time,
                    available_at,
                    float(current["High"]),
                    float(current["High"]),
                    float(current["Low"]),
                    "Bearish order block; available after next-candle impulse confirmation.",
                )
            )
    return tuple(features)


def detect_liquidity_sweeps(df: pd.DataFrame, *, window: int = 5) -> tuple[ShadowSMCFeature, ...]:
    """Detect liquidity sweeps and expose them only after reversal confirmation."""
    data = _normalize_ohlc(df)
    features: list[ShadowSMCFeature] = []
    if len(data) < window + 2:
        return ()
    for i in range(window, len(data) - 1):
        recent_high = data["High"].iloc[i - window:i].max()
        recent_low = data["Low"].iloc[i - window:i].min()
        current = data.iloc[i]
        confirmation = data.iloc[i + 1]
        event_time = pd.Timestamp(data.index[i])
        available_at = pd.Timestamp(data.index[i + 1])
        if current["High"] > recent_high and confirmation["Close"] < recent_high:
            features.append(
                ShadowSMCFeature(
                    "LIQUIDITY_SWEEP",
                    "BEARISH",
                    event_time,
                    available_at,
                    float(recent_high),
                    float(current["High"]),
                    float(recent_high),
                    "Bearish liquidity sweep; available after reversal candle.",
                )
            )
        if current["Low"] < recent_low and confirmation["Close"] > recent_low:
            features.append(
                ShadowSMCFeature(
                    "LIQUIDITY_SWEEP",
                    "BULLISH",
                    event_time,
                    available_at,
                    float(recent_low),
                    float(recent_low),
                    float(current["Low"]),
                    "Bullish liquidity sweep; available after reversal candle.",
                )
            )
    return tuple(features)


def _normalize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in ("Open", "High", "Low", "Close") if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required OHLC columns: {missing}")
    result = df.copy()
    result.index = pd.to_datetime(result.index)
    return result.dropna(subset=["Open", "High", "Low", "Close"]).sort_index()


def _round_or_none(value: float | None) -> float | None:
    return round(float(value), 4) if value is not None else None
