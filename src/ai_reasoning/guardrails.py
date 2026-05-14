"""Guardrails for advisory-only AI reasoning."""

from __future__ import annotations

from src.ai_reasoning.ai_reasoning_result import AIReasoningResult


def assert_ai_cannot_execute(result: AIReasoningResult | None = None) -> None:
    """Fail if an AI result ever claims execution permission."""
    if result is not None and bool(result.ai_can_execute):
        raise PermissionError("AI reasoning is advisory only and cannot execute trades")


def assert_allow_live_false(allow_live: bool) -> None:
    """Fail if a caller tries to enable live permissions."""
    if bool(allow_live):
        raise PermissionError("allow_live must remain false")


def assert_paper_mode_only(paper_mode: bool, allow_live: bool = False) -> None:
    """Fail unless the context is explicitly paper-only."""
    if not bool(paper_mode):
        raise PermissionError("paper_mode must remain true for this layer")
    assert_allow_live_false(allow_live)
