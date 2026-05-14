import pytest

from src.ai_reasoning.ai_decision_context import AIDecisionContext
from src.ai_reasoning.ai_reasoning_result import AIReasoningResult
from src.ai_reasoning.guardrails import (
    assert_ai_cannot_execute,
    assert_allow_live_false,
    assert_paper_mode_only,
)
from src.macro.macro_snapshot import MacroSnapshot


def test_ai_reasoning_result_cannot_execute():
    result = AIReasoningResult(
        recommendation="SUPPORT_BUY",
        confidence=0.7,
        explanation="Technical and macro context support paper BUY, advisory only.",
        warnings=("paper only",),
    )

    assert result.ai_can_execute is False
    assert_ai_cannot_execute(result)


def test_ai_reasoning_result_rejects_ai_can_execute_constructor_arg():
    with pytest.raises(TypeError):
        AIReasoningResult(ai_can_execute=True)


def test_ai_context_defaults_to_paper_only():
    context = AIDecisionContext(
        technical_score_long=82.0,
        technical_score_short=40.0,
        macro_snapshot=MacroSnapshot(),
    )

    assert context.paper_mode is True
    assert context.allow_live is False
    assert_paper_mode_only(context.paper_mode, context.allow_live)


def test_guardrails_reject_live_permissions():
    with pytest.raises(PermissionError):
        assert_allow_live_false(True)

    with pytest.raises(PermissionError):
        assert_paper_mode_only(False, allow_live=False)
