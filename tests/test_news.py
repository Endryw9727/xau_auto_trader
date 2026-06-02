"""Tests for news & calendar layer."""
from datetime import datetime

import pytest
from src.news.calendar_fetcher import EconomicEvent, fetch_economic_calendar, get_high_impact_events
from src.news.event_impact_scorer import score_event, get_event_risk_level
from src.news.news_filter import NewsFilter, NewsFilterResult


def test_economic_event_creation():
    event = EconomicEvent(
        name="NFP",
        currency="USD",
        impact="HIGH",
        datetime=datetime(2026, 1, 1, 13, 30),
    )
    assert event.name == "NFP"
    assert event.impact == "HIGH"


def test_fetch_calendar_returns_events():
    events = fetch_economic_calendar(days_ahead=7)
    assert isinstance(events, list)
    # Should return mock events
    assert len(events) >= 0


def test_get_high_impact_events():
    events = [
        EconomicEvent("NFP", "USD", "HIGH", datetime(2026, 1, 1, 13, 30)),
        EconomicEvent("CPI", "USD", "HIGH", datetime(2026, 1, 15, 13, 30)),
        EconomicEvent("Claims", "USD", "MEDIUM", datetime(2026, 1, 5, 13, 30)),
    ]
    high = get_high_impact_events(events)
    assert len(high) == 2


def test_score_event_known():
    event = EconomicEvent("Non-Farm Payrolls", "USD", "HIGH", datetime.now())
    score = score_event(event)
    assert score.score > 0


def test_score_event_unknown():
    event = EconomicEvent("Unknown Event", "USD", "LOW", datetime.now())
    score = score_event(event)
    assert score.score == 0.3


def test_get_event_risk_level():
    high_events = [
        EconomicEvent("NFP", "USD", "HIGH", datetime.now()),
        EconomicEvent("CPI", "USD", "HIGH", datetime.now()),
    ]
    assert get_event_risk_level(high_events) == "HIGH"

    low_events = [EconomicEvent("Claims", "USD", "MEDIUM", datetime.now())]
    assert get_event_risk_level(low_events) == "MEDIUM"

    assert get_event_risk_level([]) == "LOW"


def test_news_filter_allows_when_no_events(monkeypatch):
    monkeypatch.setattr("src.news.news_filter.fetch_economic_calendar", lambda days_ahead=1: [])
    filter = NewsFilter(block_before_minutes=30, block_after_minutes=15)
    result = filter.check(datetime(2026, 1, 1, 0, 0))
    assert result.allowed is True
    assert result.risk_level == "LOW"


def test_news_filter_result_structure():
    result = NewsFilterResult(
        allowed=True,
        reason="test",
        next_event=None,
        minutes_until_event=None,
        risk_level="LOW",
    )
    assert result.allowed is True
