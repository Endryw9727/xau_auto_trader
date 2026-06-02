"""Tests for calendar API."""
from datetime import datetime

from src.news.calendar_api import CalendarAPI, CalendarEvent


def test_calendar_api_mock():
    api = CalendarAPI(backend="mock")
    events = api.fetch_today()
    assert isinstance(events, list)


def test_calendar_api_high_impact():
    api = CalendarAPI(backend="mock")
    events = api.fetch_today()
    high = api.get_high_impact(events)
    assert isinstance(high, list)


def test_calendar_api_range():
    api = CalendarAPI(backend="mock")
    events = api.fetch_range(days=3)
    assert len(events) >= 0


def test_calendar_event_creation():
    event = CalendarEvent(
        name="NFP",
        currency="USD",
        impact="HIGH",
        datetime=datetime(2026, 1, 1, 13, 30),
        forecast="200K",
        previous="180K",
        actual=None,
        source="mock",
    )
    assert event.name == "NFP"
    assert event.source == "mock"
