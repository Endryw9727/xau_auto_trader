"""
AI reasoning result model.

This module defines the data structure for AI reasoning output.
The AI does not execute trades. It only provides context and warnings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AIAction = Literal["ALLOW", "BLOCK", "WARNING"]

@dataclass(frozen=True)
class AIReasoningResult:
    """Result of AI reasoning analysis."""

    action: AIAction
    confidence: float
    explanation: str
    warnings: list[str]
    technical_score: float
    fundamental_score: float
    sentiment_score: float
    session_score: float
    composite_score: float

    def __post_init__(self):
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not 0 <= self.composite_score <= 1:
            raise ValueError("composite_score must be between 0 and 1")
