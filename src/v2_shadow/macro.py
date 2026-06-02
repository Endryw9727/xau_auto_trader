"""V2-inspired macro advisory snapshot for shadow reporting.

This module does not fetch external data and never blocks/approves trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


MacroBias = Literal["BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN"]


@dataclass(frozen=True)
class ShadowMacroSnapshot:
    """Read-only macro advisory snapshot."""

    bias: MacroBias
    confidence: float
    score: float
    inputs_available: tuple[str, ...]
    explanation: str
    advisory_only: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "bias": self.bias,
            "confidence": self.confidence,
            "score": self.score,
            "inputs_available": list(self.inputs_available),
            "explanation": self.explanation,
            "advisory_only": self.advisory_only,
        }


def build_shadow_macro_snapshot(market_data: pd.DataFrame | None = None) -> ShadowMacroSnapshot:
    """Build a local-only macro proxy from available V1 data."""
    if market_data is None or market_data.empty or "Close" not in market_data.columns:
        return ShadowMacroSnapshot(
            "UNKNOWN",
            0.0,
            0.0,
            (),
            "No external macro inputs are fetched in V2 shadow mode.",
        )
    close = pd.to_numeric(market_data["Close"], errors="coerce").dropna()
    if len(close) < 30:
        return ShadowMacroSnapshot(
            "UNKNOWN",
            0.1,
            0.0,
            ("xau_close_proxy",),
            "Insufficient local candles for macro proxy; no blocking is applied.",
        )
    fast = close.ewm(span=20, adjust=False).mean().iloc[-1]
    slow = close.ewm(span=50, adjust=False).mean().iloc[-1] if len(close) >= 50 else close.rolling(30).mean().iloc[-1]
    raw_score = (fast - slow) / slow if slow else 0.0
    score = max(-1.0, min(1.0, float(raw_score) * 25.0))
    if score > 0.1:
        bias: MacroBias = "BULLISH"
    elif score < -0.1:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"
    return ShadowMacroSnapshot(
        bias,
        round(min(0.5, abs(score)), 3),
        round(score, 3),
        ("xau_close_proxy",),
        "Local XAU EMA proxy only; advisory read-only and never a live trade filter.",
    )
