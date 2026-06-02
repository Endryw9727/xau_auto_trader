"""
News filter for XAU/USD trading.

Blocks trading around high-impact economic events to avoid volatility spikes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.news.calendar_fetcher import EconomicEvent, fetch_economic_calendar, get_high_impact_events
from src.news.event_impact_scorer import get_event_risk_level

@dataclass(frozen=True)
class NewsFilterResult:
    """Result of news filter check."""

    allowed: bool
    reason: str
    next_event: EconomicEvent | None
    minutes_until_event: float | None
    risk_level: str

class NewsFilter:
    """Filter trades based on economic calendar events."""

    def __init__(
        self,
        block_before_minutes: int = 30,
        block_after_minutes: int = 15,
        block_high_impact_only: bool = True,
    ):
        self.block_before_minutes = block_before_minutes
        self.block_after_minutes = block_after_minutes
        self.block_high_impact_only = block_high_impact_only

    def check(self, timestamp: datetime | None = None) -> NewsFilterResult:
        """
        Check if trading should be allowed at the given timestamp.

        Parameters:
        - timestamp: datetime to check (default: now)

        Returns:
        - NewsFilterResult with allowed flag and reason
        """
        if timestamp is None:
            timestamp = datetime.now()

        calendar = fetch_economic_calendar(days_ahead=1)

        if self.block_high_impact_only:
            events = get_high_impact_events(calendar)
        else:
            events = calendar

        risk_level = get_event_risk_level(events)

        for event in events:
            time_diff = (event.datetime - timestamp).total_seconds() / 60

            if -self.block_after_minutes <= time_diff <= self.block_before_minutes:
                return NewsFilterResult(
                    allowed=False,
                    reason=f"Blocked: {event.name} at {event.datetime.strftime('%H:%M')} (impact: {event.impact})",
                    next_event=event,
                    minutes_until_event=time_diff,
                    risk_level=risk_level,
                )

        next_event = events[0] if events else None
        minutes_until = None
        if next_event:
            minutes_until = (next_event.datetime - timestamp).total_seconds() / 60

        return NewsFilterResult(
            allowed=True,
            reason="No blocking events in window",
            next_event=next_event,
            minutes_until_event=minutes_until,
            risk_level=risk_level,
        )

    def get_upcoming_events_summary(self, hours_ahead: int = 24) -> list[dict]:
        """Get summary of upcoming events."""
        calendar = fetch_economic_calendar(days_ahead=hours_ahead // 24 + 1)
        events = get_high_impact_events(calendar) if self.block_high_impact_only else calendar
        return [
            {
                "name": e.name,
                "time": e.datetime.strftime("%Y-%m-%d %H:%M"),
                "impact": e.impact,
                "currency": e.currency,
            }
            for e in events[:5]
        ]
