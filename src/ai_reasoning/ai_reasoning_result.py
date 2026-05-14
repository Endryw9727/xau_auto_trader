"""Output model for advisory AI reasoning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


AIRecommendation = Literal["WAIT", "SUPPORT_BUY", "SUPPORT_SELL", "BLOCK"]


@dataclass(frozen=True)
class AIReasoningResult:
    """Advisory AI result. It cannot execute by construction."""

    recommendation: AIRecommendation = "WAIT"
    confidence: float = 0.0
    explanation: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)
    ai_can_execute: bool = field(default=False, init=False)
