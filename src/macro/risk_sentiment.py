"""Risk sentiment analysis using VIX and S&P 500.

VIX (volatility index) and SPX direction help gauge risk-on / risk-off
environment, which strongly influences gold safe-haven flows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

RiskLevel = Literal["low", "normal", "high", "extreme"]
SentimentBias = Literal["risk_on", "risk_off", "neutral"]


@dataclass(frozen=True)
class RiskSentiment:
    vix_level: RiskLevel
    vix_current: float
    vix_change_1d_pct: float
    spx_bias: str  # bullish, bearish, neutral
    spx_current: float
    sentiment: SentimentBias
    gold_safe_haven_flow: str  # supportive, neutral, adverse
    notes: tuple[str, ...]


def classify_vix(vix_value: float) -> RiskLevel:
    if vix_value < 15:
        return "low"
    elif vix_value < 25:
        return "normal"
    elif vix_value < 35:
        return "high"
    else:
        return "extreme"


def analyze_risk_sentiment(vix_df: pd.DataFrame, spx_df: pd.DataFrame) -> RiskSentiment:
    """
    Analyze risk sentiment from VIX and SPX data.

    Logic:
    - High VIX + falling SPX = risk-off = bullish for gold (safe haven)
    - Low VIX + rising SPX = risk-on = neutral/bearish for gold
    - Extreme VIX = volatility regime, gold may chop but bid on dips
    """
    if vix_df.empty or "Close" not in vix_df.columns:
        return RiskSentiment(
            vix_level="normal",
            vix_current=20.0,
            vix_change_1d_pct=0.0,
            spx_bias="neutral",
            spx_current=0.0,
            sentiment="neutral",
            gold_safe_haven_flow="neutral",
            notes=("VIX data unavailable",),
        )

    vix_current = float(vix_df["Close"].iloc[-1])
    vix_prev = float(vix_df["Close"].iloc[-2]) if len(vix_df) >= 2 else vix_current
    vix_change = ((vix_current - vix_prev) / vix_prev * 100) if vix_prev != 0 else 0.0
    vix_level = classify_vix(vix_current)

    spx_bias = "neutral"
    spx_current = 0.0
    if not spx_df.empty and "Close" in spx_df.columns and len(spx_df) >= 2:
        spx_current = float(spx_df["Close"].iloc[-1])
        spx_prev = float(spx_df["Close"].iloc[-2])
        spx_change = ((spx_current - spx_prev) / spx_prev * 100) if spx_prev != 0 else 0.0
        if spx_change > 0.5:
            spx_bias = "bullish"
        elif spx_change < -0.5:
            spx_bias = "bearish"

    # Sentiment logic
    if vix_level in ("high", "extreme") and spx_bias == "bearish":
        sentiment: SentimentBias = "risk_off"
        gold_flow = "supportive"
        notes = (f"Risk-off: VIX {vix_level} ({vix_current:.1f}), SPX falling",)
    elif vix_level == "low" and spx_bias == "bullish":
        sentiment = "risk_on"
        gold_flow = "adverse"
        notes = (f"Risk-on: VIX low ({vix_current:.1f}), SPX rising",)
    elif vix_level in ("high", "extreme"):
        sentiment = "risk_off"
        gold_flow = "supportive"
        notes = (f"Elevated VIX {vix_current:.1f} supports gold bids",)
    else:
        sentiment = "neutral"
        gold_flow = "neutral"
        notes = (f"Mixed sentiment: VIX {vix_current:.1f}, SPX {spx_bias}",)

    return RiskSentiment(
        vix_level=vix_level,
        vix_current=vix_current,
        vix_change_1d_pct=vix_change,
        spx_bias=spx_bias,
        spx_current=spx_current,
        sentiment=sentiment,
        gold_safe_haven_flow=gold_flow,
        notes=notes,
    )


def fetch_vix(symbol: str = "^VIX", period: str = "1mo", interval: str = "1d") -> pd.DataFrame:
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        return df if not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def fetch_spx(symbol: str = "^GSPC", period: str = "1mo", interval: str = "1d") -> pd.DataFrame:
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        return df if not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()
