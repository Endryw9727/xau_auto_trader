"""
Score composer for AI reasoning.

Combines technical, macro, news, and session scores into a composite score.
Weights are configurable.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.ai_reasoning.context_builder import TradingContext

@dataclass(frozen=True)
class ScoreWeights:
    """Weights for composite score calculation."""

    technical: float = 0.40
    macro: float = 0.30
    news: float = 0.15
    session: float = 0.10
    risk: float = 0.05

    def __post_init__(self):
        total = self.technical + self.macro + self.news + self.session + self.risk
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

@dataclass(frozen=True)
class CompositeScore:
    """Composite score result."""

    score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    breakdown: dict[str, float]
    recommendation: str  # "STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL", "NO_TRADE"

def compose_score(context: TradingContext, weights: ScoreWeights | None = None) -> CompositeScore:
    """
    Compose a composite score from all context layers.

    Parameters:
    - context: TradingContext from build_context
    - weights: optional custom weights

    Returns:
    - CompositeScore with score, confidence, breakdown, and recommendation
    """
    weights = weights or ScoreWeights()

    # Normalize macro score to 0-1 (absolute value for strength, direction from sign)
    macro_strength = abs(context.macro_score)
    macro_direction = 1.0 if context.macro_score > 0 else (-1.0 if context.macro_score < 0 else 0.0)

    # Risk score (1.0 = healthy, 0.0 = at limits)
    risk_score = _calculate_risk_score(context)

    # Calculate weighted components
    technical_component = context.technical_score * weights.technical
    macro_component = macro_strength * weights.macro
    news_component = context.news_score * weights.news
    session_component = context.session_score * weights.session
    risk_component = risk_score * weights.risk

    raw_score = technical_component + macro_component + news_component + session_component + risk_component

    # Apply macro direction bias
    if context.signal == "BUY" and macro_direction < 0:
        raw_score *= 0.7  # Penalize buying when macro is bearish
    elif context.signal == "SELL" and macro_direction > 0:
        raw_score *= 0.7  # Penalize selling when macro is bullish

    score = max(0.0, min(1.0, raw_score))

    # Confidence based on data quality
    confidence = _calculate_confidence(context)

    # Recommendation
    recommendation = _get_recommendation(score, confidence, context)

    breakdown = {
        "technical": technical_component,
        "macro": macro_component,
        "news": news_component,
        "session": session_component,
        "risk": risk_component,
        "macro_direction": macro_direction,
    }

    return CompositeScore(
        score=round(score, 3),
        confidence=round(confidence, 3),
        breakdown=breakdown,
        recommendation=recommendation,
    )

def _calculate_risk_score(context: TradingContext) -> float:
    """Calculate risk health score."""
    score = 1.0

    if context.consecutive_losses >= 2:
        score -= 0.3
    if context.daily_loss > context.account_balance * 0.01:
        score -= 0.3
    if context.open_trades >= 2:
        score -= 0.2

    return max(0.0, score)

def _calculate_confidence(context: TradingContext) -> float:
    """Calculate confidence based on data availability."""
    confidence = 0.5

    if context.macro_result is not None:
        confidence += 0.2 * context.macro_result.confidence
    if context.news_result is not None:
        confidence += 0.1
    if context.risk_reward is not None and context.risk_reward >= 2.0:
        confidence += 0.1
    if context.adx_value is not None and context.adx_value >= 20:
        confidence += 0.1

    return min(1.0, confidence)

def _get_recommendation(score: float, confidence: float, context: TradingContext) -> str:
    """Get trade recommendation based on score and context."""
    if context.signal == "NO_TRADE":
        return "NO_TRADE"

    if confidence < 0.5:
        return "NO_TRADE"

    if score >= 0.75:
        return "STRONG_BUY" if context.signal == "BUY" else "STRONG_SELL"
    elif score >= 0.55:
        return "BUY" if context.signal == "BUY" else "SELL"
    elif score >= 0.35:
        return "WEAK_BUY" if context.signal == "BUY" else "WEAK_SELL"
    else:
        return "NO_TRADE"
