"""Macro/fundamental snapshot model for advisory context."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MacroSnapshot:
    """Advisory macro context for a technical paper-forward decision."""

    dxy_bias: str = "neutral"
    yields_bias: str = "neutral"
    news_risk: str = "unknown"
    risk_sentiment: str = "neutral"
    macro_score_long: float = 0.0
    macro_score_short: float = 0.0
    notes: tuple[str, ...] = field(default_factory=tuple)
