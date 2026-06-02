"""Tests for calendar scrapers."""
import pytest

from src.news.calendar_scrapers import ForexFactoryScraper, InvestingScraper
from src.news.calendar_api import CalendarAPI, CalendarEvent


def test_forex_factory_scraper_init():
    scraper = ForexFactoryScraper()
    assert scraper.timeout == 15


def test_forex_factory_is_gold_relevant():
    assert ForexFactoryScraper._is_gold_relevant("Non-Farm Payrolls") is True
    assert ForexFactoryScraper._is_gold_relevant("CPI m/m") is True
    assert ForexFactoryScraper._is_gold_relevant("Random Event") is False


def test_investing_scraper_init():
    scraper = InvestingScraper()
    assert scraper.timeout == 15


def test_calendar_api_mock():
    api = CalendarAPI(backend="mock")
    events = api.fetch_today()
    assert isinstance(events, list)
    assert all(isinstance(e, CalendarEvent) for e in events)


def test_calendar_api_mock_range():
    api = CalendarAPI(backend="mock")
    events = api.fetch_range(days=3)
    assert len(events) >= 0
    # Events should be sorted by datetime
    for i in range(1, len(events)):
        assert events[i].datetime >= events[i-1].datetime


def test_calendar_api_high_impact():
    api = CalendarAPI(backend="mock")
    events = api.fetch_today()
    high = api.get_high_impact(events)
    assert all(e.impact == "HIGH" for e in high)


def test_calendar_api_next_event():
    api = CalendarAPI(backend="mock")
    events = api.fetch_today()
    next_event = api.get_next_event(events)
    # May be None if no future events
    assert next_event is None or isinstance(next_event, CalendarEvent)
