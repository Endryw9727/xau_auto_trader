"""
Economic calendar fetcher.

Legacy module — now delegates to CalendarAPI.
Kept for backward compatibility.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from src.news.calendar_api import CalendarAPI, CalendarEvent

EventImpact = Literal["HIGH", "MEDIUM", "LOW"]

# Re-export for backward compatibility
EconomicEvent = CalendarEvent


def fetch_economic_calendar(days_ahead: int = 7) -> list[CalendarEvent]:
    """
    Fetch economic calendar events.

    Parameters:
    - days_ahead: number of days to look ahead

    Returns:
    - List of CalendarEvent objects
    """
    api = CalendarAPI(backend="mock")
    return api.fetch_range(days_ahead)


def get_high_impact_events(calendar: list[CalendarEvent]) -> list[CalendarEvent]:
    """Filter for high-impact events only."""
    return [e for e in calendar if e.impact == "HIGH"]


def event_to_dict(event: CalendarEvent) -> dict:
    """Convert event to dictionary."""
    return {
        "name": event.name,
        "currency": event.currency,
        "impact": event.impact,
        "datetime": event.datetime.isoformat(),
        "forecast": event.forecast,
        "previous": event.previous,
        "actual": event.actual,
        "source": event.source,
    }
