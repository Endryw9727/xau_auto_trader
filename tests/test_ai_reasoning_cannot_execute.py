"""Test that AI reasoning cannot execute trades."""
from src.ai_reasoning.guardrails import AIReasoningGuardrails, GuardrailsConfig

def test_ai_cannot_execute_trades():
    config = GuardrailsConfig(allow_trade_execution=False)
    guardrails = AIReasoningGuardrails(config)

    result = guardrails.validate_recommendation(0.9, "ALLOW")
    assert result["allowed"] is True
    assert "trade execution is disabled" not in result["reason"]

    # Verify the guardrail blocks execution
    assert config.allow_trade_execution is False
