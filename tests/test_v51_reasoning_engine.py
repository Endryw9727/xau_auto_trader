from src.ai_reasoning.v51_reasoning_engine import (
    CandidateContext,
    ReasoningInput,
    TimeframeContext,
    evaluate_v51_reasoning,
)


def tf(timeframe, direction, *, used=True):
    return TimeframeContext(
        timeframe=timeframe,
        trend_direction=direction,
        ema_alignment=direction,
        data_status="OK",
        used_in_bias=used,
        distance_from_support=3.0,
        distance_from_resistance=6.0,
        volatility_regime="NORMAL",
    )


def candidate(side, *, spread=10.0, slippage=2.0, score=86.0):
    return CandidateContext(
        side=side,
        score=score,
        score_gap=18.0,
        risk_reward=1.5,
        session="NEW YORK",
        spread_points=spread,
        max_spread_points=80.0,
        slippage_points=slippage,
        max_slippage_points=20.0,
        expected_entry_price=2400.0,
    )


def test_v51_reasoning_engine_no_trade_on_mixed_mtf():
    decision = evaluate_v51_reasoning(
        ReasoningInput(
            timeframes=(tf("D1", "BULL"), tf("H4", "BEAR"), tf("H1", "BULL"), tf("M15", "BEAR")),
            candidate=candidate("BUY"),
            mtf_final_bias="MIXED",
        )
    )

    assert decision.final_bias == "MIXED"
    assert decision.allow_trade is False
    assert "mtf_context_not_directional" in decision.veto_reasons


def test_v51_reasoning_engine_allows_high_quality_short_setup():
    decision = evaluate_v51_reasoning(
        ReasoningInput(
            timeframes=(
                tf("D1", "BEAR"),
                tf("H4", "BEAR"),
                tf("H1", "BEAR"),
                tf("M15", "BEAR"),
                tf("M5", "BEAR"),
                tf("M1", "BEAR"),
            ),
            candidate=candidate("SELL"),
            mtf_final_bias="SHORT_BIAS",
        )
    )

    assert decision.final_bias == "SHORT_BIAS"
    assert decision.allow_trade is True
    assert decision.confidence_score >= 70
    assert decision.trade_quality_score >= 70


def test_v51_reasoning_engine_allows_high_quality_long_setup():
    decision = evaluate_v51_reasoning(
        ReasoningInput(
            timeframes=(
                tf("D1", "BULL"),
                tf("H4", "BULL"),
                tf("H1", "BULL"),
                tf("M15", "BULL"),
                tf("M5", "BULL"),
                tf("M1", "BULL"),
            ),
            candidate=candidate("BUY"),
            mtf_final_bias="LONG_BIAS",
        )
    )

    assert decision.final_bias == "LONG_BIAS"
    assert decision.allow_trade is True
    assert decision.confidence_score >= 70
    assert decision.trade_quality_score >= 70


def test_v51_reasoning_engine_vetoes_excessive_spread_slippage():
    decision = evaluate_v51_reasoning(
        ReasoningInput(
            timeframes=(tf("D1", "BEAR"), tf("H4", "BEAR"), tf("H1", "BEAR"), tf("M15", "BEAR")),
            candidate=candidate("SELL", spread=100.0, slippage=30.0),
            mtf_final_bias="SHORT_BIAS",
        )
    )

    assert decision.allow_trade is False
    assert "spread_too_high" in decision.veto_reasons
    assert "slippage_too_high" in decision.veto_reasons
