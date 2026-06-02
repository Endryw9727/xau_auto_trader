"""Tests for AI reasoning engine."""
import pandas as pd
import pytest

from src.ai_reasoning.context_builder import TradingContext, build_context
from src.ai_reasoning.score_composer import ScoreWeights, CompositeScore, compose_score
from src.ai_reasoning.explanation_engine import generate_explanation, generate_summary
from src.ai_reasoning.warning_system import Warning, generate_warnings, should_block
from src.macro.macro_engine import MacroAnalysisResult
from src.macro.macro_snapshot import MacroSnapshot
from src.news.news_filter import NewsFilterResult


def test_score_weights_validation():
    weights = ScoreWeights()
    assert abs(weights.technical + weights.macro + weights.news + weights.session + weights.risk - 1.0) < 0.001


def test_score_weights_invalid():
    with pytest.raises(ValueError, match="Weights must sum to 1.0"):
        ScoreWeights(technical=1.0, macro=0.5)


def test_build_context_basic():
    df = pd.DataFrame({
        "Open": [1]*300, "High": [2]*300, "Low": [0.5]*300,
        "Close": [1.5]*300, "Volume": [100]*300,
    }, index=pd.date_range("2026-01-01", periods=300, freq="15min"))

    signal_row = pd.Series({
        "Close": 1.5, "signal": "BUY", "entry": 1.5, "stop_loss": 1.0,
        "take_profit": 2.5, "risk_reward": 2.0, "ADX_14": 25.0, "RSI_14": 50.0,
    })

    context = build_context(
        df=df,
        signal_row=signal_row,
        macro_result=None,
        news_result=None,
        account_balance=1000,
        open_trades=0,
        daily_loss=0.0,
        consecutive_losses=0,
    )

    assert context.signal == "BUY"
    assert context.technical_score > 0
    assert context.current_session in {"Asia", "London", "New York", "Off Session"}


def test_compose_score_buy_signal():
    context = TradingContext(
        current_price=2350.0,
        trend="UP",
        structure={"trend": "UP"},
        signal="BUY",
        entry=2350.0,
        stop_loss=2340.0,
        take_profit=2370.0,
        risk_reward=2.0,
        adx_value=25.0,
        rsi_value=50.0,
        macro_result=None,
        news_result=None,
        current_session="London",
        session_volatility="high",
        account_balance=1000,
        open_trades=0,
        daily_loss=0.0,
        consecutive_losses=0,
        technical_score=0.8,
        macro_score=0.2,
        news_score=1.0,
        session_score=1.0,
    )

    score = compose_score(context)
    assert isinstance(score, CompositeScore)
    assert 0 <= score.score <= 1
    assert score.recommendation in {"STRONG_BUY", "BUY", "WEAK_BUY", "NO_TRADE"}


def test_generate_explanation_not_empty():
    context = TradingContext(
        current_price=2350.0,
        trend="UP",
        structure={"trend": "UP"},
        signal="BUY",
        entry=2350.0,
        stop_loss=2340.0,
        take_profit=2370.0,
        risk_reward=2.0,
        adx_value=25.0,
        rsi_value=50.0,
        macro_result=None,
        news_result=None,
        current_session="London",
        session_volatility="high",
        account_balance=1000,
        open_trades=0,
        daily_loss=0.0,
        consecutive_losses=0,
        technical_score=0.8,
        macro_score=0.0,
        news_score=1.0,
        session_score=1.0,
    )
    score = compose_score(context)
    explanation = generate_explanation(context, score)
    assert "XAU/USD" in explanation
    assert "PRICE" in explanation


def test_generate_warnings_blocks_on_news():
    context = TradingContext(
        current_price=2350.0,
        trend="UP",
        structure={},
        signal="BUY",
        entry=2350.0,
        stop_loss=2340.0,
        take_profit=2370.0,
        risk_reward=2.0,
        adx_value=25.0,
        rsi_value=50.0,
        macro_result=None,
        news_result=NewsFilterResult(
            allowed=False,
            reason="NFP in 15 minutes",
            next_event=None,
            minutes_until_event=15.0,
            risk_level="HIGH",
        ),
        current_session="London",
        session_volatility="high",
        account_balance=1000,
        open_trades=0,
        daily_loss=0.0,
        consecutive_losses=0,
        technical_score=0.8,
        macro_score=0.0,
        news_score=0.0,
        session_score=1.0,
    )
    score = compose_score(context)
    warnings = generate_warnings(context, score)
    blocked, reason = should_block(warnings)
    assert blocked is True
    assert "NFP" in reason


def test_warning_levels():
    w = Warning(level="CRITICAL", category="NEWS", message="test", action="BLOCK")
    assert w.level == "CRITICAL"
    assert w.action == "BLOCK"
