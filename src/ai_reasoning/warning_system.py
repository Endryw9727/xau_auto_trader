"""
Warning system for AI reasoning.

Generates conditional warnings based on context analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.ai_reasoning.context_builder import TradingContext
from src.ai_reasoning.score_composer import CompositeScore

WarningLevel = Literal["INFO", "WARNING", "CRITICAL"]

@dataclass(frozen=True)
class Warning:
    """A trading warning."""

    level: WarningLevel
    category: str
    message: str
    action: str  # "PROCEED", "CAUTION", "BLOCK"

def generate_warnings(context: TradingContext, score: CompositeScore) -> list[Warning]:
    """
    Generate warnings based on trading context and composite score.

    Parameters:
    - context: TradingContext
    - score: CompositeScore

    Returns:
    - List of Warning objects
    """
    warnings: list[Warning] = []

    # Macro warnings
    if context.macro_result:
        if context.signal == "BUY" and context.macro_result.score <= -0.4:
            warnings.append(Warning(
                level="WARNING",
                category="MACRO",
                message=f"Buying into strong macro bearish bias ({context.macro_result.score:+.2f})",
                action="CAUTION",
            ))
        elif context.signal == "SELL" and context.macro_result.score >= 0.4:
            warnings.append(Warning(
                level="WARNING",
                category="MACRO",
                message=f"Selling into strong macro bullish bias ({context.macro_result.score:+.2f})",
                action="CAUTION",
            ))

        if context.macro_result.dxy_correlation is not None:
            corr = context.macro_result.dxy_correlation
            if abs(corr) >= 0.8:
                warnings.append(Warning(
                    level="INFO",
                    category="CORRELATION",
                    message=f"Strong XAU/DXY correlation: {corr:.2f}",
                    action="PROCEED",
                ))

    # News warnings
    if context.news_result and not context.news_result.allowed:
        warnings.append(Warning(
            level="CRITICAL",
            category="NEWS",
            message=f"News filter blocked: {context.news_result.reason}",
            action="BLOCK",
        ))
    elif context.news_result and context.news_result.risk_level == "HIGH":
        warnings.append(Warning(
            level="WARNING",
            category="NEWS",
            message="High-impact events approaching — expect volatility",
            action="CAUTION",
        ))

    # Risk warnings
    if context.consecutive_losses >= 2:
        warnings.append(Warning(
            level="WARNING",
            category="RISK",
            message=f"Consecutive losses: {context.consecutive_losses} — reduce size or pause",
            action="CAUTION",
        ))

    if context.daily_loss > context.account_balance * 0.015:
        warnings.append(Warning(
            level="CRITICAL",
            category="RISK",
            message=f"Daily loss approaching limit: {context.daily_loss:.2f}",
            action="BLOCK",
        ))

    if context.open_trades >= 2:
        warnings.append(Warning(
            level="INFO",
            category="RISK",
            message=f"Max open trades reached: {context.open_trades}",
            action="PROCEED",
        ))

    # Technical warnings
    if context.adx_value is not None and context.adx_value < 20:
        warnings.append(Warning(
            level="WARNING",
            category="TECHNICAL",
            message=f"Low ADX ({context.adx_value:.1f}) — weak trend, avoid chasing",
            action="CAUTION",
        ))

    if context.risk_reward is not None and context.risk_reward < 2.0:
        warnings.append(Warning(
            level="WARNING",
            category="TECHNICAL",
            message=f"Low R:R ({context.risk_reward:.2f}) — below minimum threshold",
            action="BLOCK",
        ))

    # Session warnings
    if context.current_session == "Asia" and context.signal != "NO_TRADE":
        warnings.append(Warning(
            level="INFO",
            category="SESSION",
            message="Asia session — lower liquidity, wider spreads possible",
            action="CAUTION",
        ))

    # Score warnings
    if score.confidence < 0.6:
        warnings.append(Warning(
            level="WARNING",
            category="CONFIDENCE",
            message=f"Low confidence ({score.confidence:.0%}) — insufficient data",
            action="CAUTION",
        ))

    if score.score < 0.4 and context.signal != "NO_TRADE":
        warnings.append(Warning(
            level="WARNING",
            category="SCORE",
            message=f"Low composite score ({score.score:.2f}) — setup quality poor",
            action="CAUTION",
        ))

    return warnings

def should_block(warnings: list[Warning]) -> tuple[bool, str | None]:
    """Check if any warning requires blocking the trade."""
    blockers = [w for w in warnings if w.action == "BLOCK"]
    if blockers:
        return True, " | ".join(f"[{w.category}] {w.message}" for w in blockers)
    return False, None
