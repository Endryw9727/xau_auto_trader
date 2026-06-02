"""
Real economic calendar API interface.

Supports multiple backends:
- forex_factory: Web scraping (requires beautifulsoup4, lxml)
- investing: Web scraping (requires beautifulsoup4, lxml)
- mock: Deterministic mock data for testing

Usage:
    from src.news.calendar_api import CalendarAPI
    api = CalendarAPI(backend="forex_factory")
    events = api.fetch_today()
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

CalendarBackend = Literal["mock", "forex_factory", "investing"]

@dataclass(frozen=True)
class CalendarEvent:
    """Standardized calendar event from any backend."""

    name: str
    currency: str
    impact: str  # "HIGH", "MEDIUM", "LOW"
    datetime: datetime
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None
    source: str = "mock"


class CalendarAPI:
    """Unified calendar API with pluggable backends."""

    def __init__(self, backend: CalendarBackend = "mock"):
        self.backend = backend
        self._scraper = None

    def fetch_today(self) -> list[CalendarEvent]:
        """Fetch events for today."""
        if self.backend == "mock":
            return self._fetch_mock()
        elif self.backend == "forex_factory":
            return self._fetch_forex_factory()
        elif self.backend == "investing":
            return self._fetch_investing()
        else:
            raise ValueError(f"Unknown backend: {self.backend}")

    def fetch_range(self, days: int = 7) -> list[CalendarEvent]:
        """Fetch events for the next N days."""
        if self.backend == "mock":
            return self._fetch_mock_range(days)

        # For real scrapers, fetch each day
        all_events = []
        for i in range(days):
            date = datetime.now() + timedelta(days=i)
            try:
                if self.backend == "forex_factory":
                    from src.news.calendar_scrapers import ForexFactoryScraper
                    scraper = ForexFactoryScraper()
                    day_events = scraper.fetch_date(date)
                    all_events.extend(day_events)
                elif self.backend == "investing":
                    # Investing.com doesn't support date range easily
                    day_events = self._fetch_investing()
                    all_events.extend(day_events)
            except Exception as e:
                print(f"Warning: Failed to fetch day {i}: {e}")
                continue

        return sorted(all_events, key=lambda e: e.datetime)

    def _fetch_mock(self) -> list[CalendarEvent]:
        """Return mock events for today."""
        return self._generate_mock_day(0)

    def _fetch_mock_range(self, days: int) -> list[CalendarEvent]:
        """Generate mock events for N days."""
        all_events = []
        for i in range(days):
            all_events.extend(self._generate_mock_day(i))
        return sorted(all_events, key=lambda e: e.datetime)

    def _fetch_forex_factory(self) -> list[CalendarEvent]:
        """Fetch from ForexFactory."""
        try:
            from src.news.calendar_scrapers import ForexFactoryScraper
            scraper = ForexFactoryScraper()
            return scraper.fetch_today()
        except ImportError as e:
            raise ImportError(
                "ForexFactory scraper requires beautifulsoup4 and lxml. "
                "Install: pip install beautifulsoup4 lxml"
            ) from e
        except Exception as e:
            raise RuntimeError(f"ForexFactory scraper failed: {e}")

    def _fetch_investing(self) -> list[CalendarEvent]:
        """Fetch from Investing.com."""
        try:
            from src.news.calendar_scrapers import InvestingScraper
            scraper = InvestingScraper()
            return scraper.fetch_today()
        except ImportError as e:
            raise ImportError(
                "Investing.com scraper requires beautifulsoup4 and lxml. "
                "Install: pip install beautifulsoup4 lxml"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Investing.com scraper failed: {e}")

    def _generate_mock_day(self, day_offset: int = 0) -> list[CalendarEvent]:
        """Generate realistic mock events for a given day offset."""
        base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        day = base + timedelta(days=day_offset)

        templates = [
            ("Non-Farm Payrolls", "USD", "HIGH", 13, 30),
            ("Unemployment Rate", "USD", "HIGH", 13, 30),
            ("CPI m/m", "USD", "HIGH", 13, 30),
            ("Core CPI m/m", "USD", "HIGH", 13, 30),
            ("FOMC Statement", "USD", "HIGH", 19, 0),
            ("Fed Interest Rate Decision", "USD", "HIGH", 19, 0),
            ("Fed Chair Powell Speech", "USD", "HIGH", 14, 0),
            ("Retail Sales m/m", "USD", "HIGH", 13, 30),
            ("Core Retail Sales m/m", "USD", "MEDIUM", 13, 30),
            ("GDP q/q", "USD", "HIGH", 13, 30),
            ("ISM Manufacturing PMI", "USD", "MEDIUM", 15, 0),
            ("ISM Services PMI", "USD", "MEDIUM", 15, 0),
            ("ADP Non-Farm Employment", "USD", "MEDIUM", 13, 15),
            ("Initial Jobless Claims", "USD", "MEDIUM", 13, 30),
            ("PPI m/m", "USD", "MEDIUM", 13, 30),
            ("Core PPI m/m", "USD", "MEDIUM", 13, 30),
            ("Building Permits", "USD", "LOW", 13, 30),
            ("Existing Home Sales", "USD", "LOW", 15, 0),
            ("Consumer Confidence", "USD", "MEDIUM", 15, 0),
            ("Durable Goods Orders m/m", "USD", "MEDIUM", 13, 30),
        ]

        events = []
        for name, currency, impact, hour, minute in templates:
            if hash(name + str(day.date())) % 7 == 0:
                event_time = day.replace(hour=hour, minute=minute)
                events.append(CalendarEvent(
                    name=name,
                    currency=currency,
                    impact=impact,
                    datetime=event_time,
                    forecast=None,
                    previous=None,
                    actual=None,
                    source="mock",
                ))

        return events

    def get_high_impact(self, events: list[CalendarEvent] | None = None) -> list[CalendarEvent]:
        """Filter for high-impact events only."""
        if events is None:
            events = self.fetch_today()
        return [e for e in events if e.impact == "HIGH"]

    def get_next_event(self, events: list[CalendarEvent] | None = None) -> CalendarEvent | None:
        """Get the next upcoming event."""
        if events is None:
            events = self.fetch_today()
        now = datetime.now()
        future = [e for e in events if e.datetime > now]
        return min(future, key=lambda e: e.datetime) if future else None
