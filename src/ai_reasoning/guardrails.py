"""
AI reasoning guardrails.

This module ensures the AI reasoning engine cannot execute trades.
It can only provide analysis, warnings, and recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class GuardrailsConfig:
    """Configuration for AI guardrails."""

    allow_trade_execution: bool = False
    max_warnings_per_analysis: int = 5
    min_confidence_for_recommendation: float = 0.7

class AIReasoningGuardrails:
    """Guardrails to prevent AI from executing trades."""

    def __init__(self, config: GuardrailsConfig):
        self.config = config

    def validate_recommendation(self, confidence: float, action: str) -> dict:
        """Validate an AI recommendation against guardrails."""
        if self.config.allow_trade_execution:
            return {"allowed": False, "reason": "AI trade execution is disabled"}

        if confidence < self.config.min_confidence_for_recommendation:
            return {"allowed": False, "reason": f"Confidence too low ({confidence:.2f} < {self.config.min_confidence_for_recommendation})"}

        if action not in {"ALLOW", "BLOCK", "WARNING"}:
            return {"allowed": False, "reason": f"Invalid action: {action}"}

        return {"allowed": True, "reason": "Recommendation validated"}
