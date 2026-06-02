"""
Explanation engine for AI reasoning.

Generates human-readable explanations for trading decisions.
"""

from __future__ import annotations

from src.ai_reasoning.context_builder import TradingContext
from src.ai_reasoning.score_composer import CompositeScore

def generate_explanation(context: TradingContext, score: CompositeScore) -> str:
    """
    Generate a human-readable explanation of the trading analysis.

    Parameters:
    - context: TradingContext
    - score: CompositeScore

    Returns:
    - Multi-line string explanation
    """
    lines = []

    # Header
    lines.append("=" * 50)
    lines.append("XAU/USD TRADING ANALYSIS")
    lines.append("=" * 50)

    # Price & Signal
    lines.append(f"\n📊 PRICE: {context.current_price:.2f}")
    lines.append(f"📈 SIGNAL: {context.signal}")
    if context.entry:
        lines.append(f"   Entry: {context.entry:.2f}")
    if context.stop_loss:
        lines.append(f"   Stop: {context.stop_loss:.2f}")
    if context.take_profit:
        lines.append(f"   Target: {context.take_profit:.2f}")
    if context.risk_reward:
        lines.append(f"   R:R = 1:{context.risk_reward:.2f}")

    # Technical
    lines.append(f"\n🔧 TECHNICAL (score: {context.technical_score:.2f})")
    lines.append(f"   Trend: {context.trend}")
    if context.adx_value:
        lines.append(f"   ADX: {context.adx_value:.1f}")
    if context.rsi_value:
        lines.append(f"   RSI: {context.rsi_value:.1f}")

    # Structure
    lines.append(f"\n🏗️  STRUCTURE")
    for key, value in context.structure.items():
        if value is not None:
            lines.append(f"   {key}: {value}")

    # Macro
    if context.macro_result:
        lines.append(f"\n🌍 MACRO (score: {context.macro_score:+.2f})")
        lines.append(f"   Bias: {context.macro_result.score_label}")
        lines.append(f"   Confidence: {context.macro_result.confidence:.0%}")
        lines.append(f"   {context.macro_result.explanation}")
    else:
        lines.append("\n🌍 MACRO: No data available")

    # News
    if context.news_result:
        lines.append(f"\n📰 NEWS")
        if context.news_result.allowed:
            lines.append(f"   ✅ Trading allowed")
            if context.news_result.next_event:
                lines.append(f"   Next event: {context.news_result.next_event.name} in {context.news_result.minutes_until_event:.0f}min")
        else:
            lines.append(f"   ❌ BLOCKED: {context.news_result.reason}")
        lines.append(f"   Risk level: {context.news_result.risk_level}")
    else:
        lines.append("\n📰 NEWS: No filter applied")

    # Session
    lines.append(f"\n⏰ SESSION: {context.current_session} (volatility: {context.session_volatility})")
    lines.append(f"   Session score: {context.session_score:.2f}")

    # Risk
    lines.append(f"\n⚠️  RISK STATUS")
    lines.append(f"   Balance: {context.account_balance:.2f}")
    lines.append(f"   Open trades: {context.open_trades}")
    lines.append(f"   Daily loss: {context.daily_loss:.2f}")
    lines.append(f"   Consecutive losses: {context.consecutive_losses}")

    # Composite Score
    lines.append(f"\n🎯 COMPOSITE SCORE: {score.score:.2f}/1.00")
    lines.append(f"   Confidence: {score.confidence:.0%}")
    lines.append(f"   Recommendation: {score.recommendation}")

    lines.append(f"\n📊 Score Breakdown:")
    for component, value in score.breakdown.items():
        lines.append(f"   {component}: {value:.3f}")

    lines.append("\n" + "=" * 50)

    return "\n".join(lines)

def generate_summary(context: TradingContext, score: CompositeScore) -> str:
    """Generate a one-line summary."""
    parts = [
        f"{context.signal}",
        f"RR={context.risk_reward:.1f}" if context.risk_reward else "no RR",
        f"score={score.score:.2f}",
        f"conf={score.confidence:.0%}",
        f"rec={score.recommendation}",
    ]
    return " | ".join(parts)
