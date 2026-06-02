"""
Event impact scorer.

Scores the potential market impact of economic events on XAU/USD.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.news.calendar_fetcher import EconomicEvent, EventImpact

@dataclass(frozen=True)
class ImpactScore:
    """Impact score for an event."""

    score: float  # 0.0 to 1.0
    direction_bias: str  # "bullish", "bearish", "neutral" for gold
    reasoning: str

EVENT_IMPACT_MAP = {
    "Non-Farm Payrolls": {
        "better_than_expected": ImpactScore(0.8, "bearish", "Strong jobs = stronger USD = lower gold"),
        "worse_than_expected": ImpactScore(0.8, "bullish", "Weak jobs = weaker USD = higher gold"),
    },
    "CPI m/m": {
        "higher_than_expected": ImpactScore(0.9, "bearish", "High inflation = hawkish Fed = stronger USD"),
        "lower_than_expected": ImpactScore(0.9, "bullish", "Low inflation = dovish Fed = weaker USD"),
    },
    "FOMC Statement": {
        "hawkish": ImpactScore(0.95, "bearish", "Hawkish Fed = stronger USD = lower gold"),
        "dovish": ImpactScore(0.95, "bullish", "Dovish Fed = weaker USD = higher gold"),
    },
    "Fed Chair Powell Speech": {
        "hawkish": ImpactScore(0.7, "bearish", "Hawkish tone = stronger USD"),
        "dovish": ImpactScore(0.7, "bullish", "Dovish tone = weaker USD"),
    },
    "Retail Sales m/m": {
        "better": ImpactScore(0.6, "bearish", "Strong retail = strong economy = strong USD"),
        "worse": ImpactScore(0.6, "bullish", "Weak retail = weak economy = weak USD"),
    },
    "GDP q/q": {
        "better": ImpactScore(0.7, "bearish", "Strong GDP = strong USD"),
        "worse": ImpactScore(0.7, "bullish", "Weak GDP = weak USD"),
    },
}

def score_event(event: EconomicEvent, outcome: str | None = None) -> ImpactScore:
    """
    Score an economic event's potential impact on XAU/USD.

    Parameters:
    - event: the economic event
    - outcome: optional outcome description (e.g. "better_than_expected")

    Returns:
    - ImpactScore with score and direction bias
    """
    if event.name not in EVENT_IMPACT_MAP:
        return ImpactScore(0.3, "neutral", f"Unknown event: {event.name}")

    mapping = EVENT_IMPACT_MAP[event.name]

    if outcome and outcome in mapping:
        return mapping[outcome]

    # Default: return the first available score as baseline
    first_key = list(mapping.keys())[0]
    return ImpactScore(
        score=mapping[first_key].score * 0.5,  # Halve confidence without outcome
        direction_bias="neutral",
        reasoning=f"{event.name}: outcome unknown, potential impact uncertain",
    )

def get_event_risk_level(events: list[EconomicEvent]) -> str:
    """
    Determine overall event risk level for the next period.

    Returns: "HIGH", "MEDIUM", "LOW"
    """
    if not events:
        return "LOW"

    high_count = sum(1 for e in events if e.impact == "HIGH")
    medium_count = sum(1 for e in events if e.impact == "MEDIUM")

    if high_count >= 2:
        return "HIGH"
    elif high_count == 1:
        return "MEDIUM"
    elif medium_count > 0:
        return "MEDIUM"
    return "LOW"
