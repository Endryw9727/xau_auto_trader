"""
Context builder for AI reasoning.

Aggregates all layers (technical, macro, news, session) into a unified context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.macro.macro_engine import MacroAnalysisResult
from src.news.news_filter import NewsFilterResult
from src.strategy.structure import analyze_structure

@dataclass(frozen=True)
class TradingContext:
    """Unified trading context for AI reasoning."""

    # Technical
    current_price: float
    trend: str
    structure: dict[str, Any]
    signal: str
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None
    adx_value: float | None
    rsi_value: float | None

    # Macro
    macro_result: MacroAnalysisResult | None

    # News
    news_result: NewsFilterResult | None

    # Session
    current_session: str
    session_volatility: str  # "high", "medium", "low"

    # Risk
    account_balance: float
    open_trades: int
    daily_loss: float
    consecutive_losses: int

    # Composite
    technical_score: float  # 0.0 to 1.0
    macro_score: float  # -1.0 to 1.0
    news_score: float  # 0.0 to 1.0 (1.0 = safe to trade)
    session_score: float  # 0.0 to 1.0

def build_context(
    df: pd.DataFrame,
    signal_row: pd.Series,
    macro_result: MacroAnalysisResult | None,
    news_result: NewsFilterResult | None,
    account_balance: float,
    open_trades: int,
    daily_loss: float,
    consecutive_losses: int,
) -> TradingContext:
    """
    Build a unified trading context from all available data layers.

    Parameters:
    - df: OHLCV DataFrame with indicators
    - signal_row: current signal row from signals_df
    - macro_result: macro analysis result
    - news_result: news filter result
    - account_balance: current balance
    - open_trades: number of open trades
    - daily_loss: current daily loss
    - consecutive_losses: current consecutive losses

    Returns:
    - TradingContext dataclass
    """
    from src.analysis.session_analysis import classify_session

    timestamp = df.index[-1] if not df.empty else pd.Timestamp.now()
    current_session = classify_session(timestamp)

    structure = analyze_structure(df)

    # Technical score calculation
    technical_score = _calculate_technical_score(signal_row, structure)

    # Macro score (normalized to 0-1 for bullish, 0 for neutral, 0-1 for bearish)
    macro_score = macro_result.score if macro_result else 0.0

    # News score (1.0 = safe, 0.0 = blocked)
    news_score = 1.0 if (news_result is None or news_result.allowed) else 0.0

    # Session score
    session_score = _calculate_session_score(current_session)

    return TradingContext(
        current_price=float(signal_row.get("Close", 0)),
        trend=structure.get("trend", "NEUTRAL"),
        structure=structure,
        signal=str(signal_row.get("signal", "NO_TRADE")),
        entry=float(signal_row.get("entry", 0)) if pd.notna(signal_row.get("entry")) else None,
        stop_loss=float(signal_row.get("stop_loss", 0)) if pd.notna(signal_row.get("stop_loss")) else None,
        take_profit=float(signal_row.get("take_profit", 0)) if pd.notna(signal_row.get("take_profit")) else None,
        risk_reward=float(signal_row.get("risk_reward", 0)) if pd.notna(signal_row.get("risk_reward")) else None,
        adx_value=float(signal_row.get("ADX_14", 0)) if pd.notna(signal_row.get("ADX_14")) else None,
        rsi_value=float(signal_row.get("RSI_14", 0)) if pd.notna(signal_row.get("RSI_14")) else None,
        macro_result=macro_result,
        news_result=news_result,
        current_session=current_session,
        session_volatility=_get_session_volatility(current_session),
        account_balance=account_balance,
        open_trades=open_trades,
        daily_loss=daily_loss,
        consecutive_losses=consecutive_losses,
        technical_score=technical_score,
        macro_score=macro_score,
        news_score=news_score,
        session_score=session_score,
    )

def _calculate_technical_score(signal_row: pd.Series, structure: dict) -> float:
    """Calculate technical score from 0.0 to 1.0."""
    score = 0.0

    signal = str(signal_row.get("signal", "NO_TRADE"))
    if signal in {"BUY", "SELL"}:
        score += 0.4

    rr = signal_row.get("risk_reward")
    if pd.notna(rr) and float(rr) >= 2.0:
        score += 0.3
    elif pd.notna(rr) and float(rr) >= 1.5:
        score += 0.15

    adx = signal_row.get("ADX_14")
    if pd.notna(adx) and float(adx) >= 25:
        score += 0.2
    elif pd.notna(adx) and float(adx) >= 18:
        score += 0.1

    trend = structure.get("trend", "NEUTRAL")
    if trend != "NEUTRAL":
        score += 0.1

    return min(1.0, score)

def _calculate_session_score(session: str) -> float:
    """Score session favorability for XAU/USD."""
    scores = {
        "London": 1.0,
        "New York": 0.9,
        "Asia": 0.5,
        "Off Session": 0.3,
    }
    return scores.get(session, 0.5)

def _get_session_volatility(session: str) -> str:
    """Classify session volatility."""
    vol_map = {
        "London": "high",
        "New York": "high",
        "Asia": "low",
        "Off Session": "low",
    }
    return vol_map.get(session, "medium")
