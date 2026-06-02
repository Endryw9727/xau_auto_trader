"""
Real economic calendar scrapers for ForexFactory and Investing.com.

Implements robust HTML scraping with BeautifulSoup fallback.
Requires: requests, beautifulsoup4, lxml

Usage:
    from src.news.calendar_scrapers import ForexFactoryScraper, InvestingScraper
    events = ForexFactoryScraper().fetch_today()
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import requests
from bs4 import BeautifulSoup

from src.news.calendar_api import CalendarEvent

EventImpact = Literal["HIGH", "MEDIUM", "LOW"]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


class ForexFactoryScraper:
    """Scraper for ForexFactory economic calendar."""

    BASE_URL = "https://www.forexfactory.com/calendar"
    TABLE_URL = "https://www.forexfactory.com/calendar?day=today"

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_today(self) -> list[CalendarEvent]:
        """Fetch today's events from ForexFactory."""
        try:
            response = self.session.get(self.TABLE_URL, timeout=self.timeout)
            response.raise_for_status()
            return self._parse_html(response.text)
        except Exception as e:
            raise RuntimeError(f"ForexFactory fetch failed: {e}")

    def fetch_date(self, date: datetime) -> list[CalendarEvent]:
        """Fetch events for a specific date."""
        url = f"{self.BASE_URL}?day={date.strftime('%b%d.%Y')}"
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return self._parse_html(response.text)
        except Exception as e:
            raise RuntimeError(f"ForexFactory fetch failed for {date}: {e}")

    def _parse_html(self, html: str) -> list[CalendarEvent]:
        """Parse ForexFactory HTML into CalendarEvent objects."""
        soup = BeautifulSoup(html, "lxml")
        events: list[CalendarEvent] = []

        # Find the calendar table
        table = soup.find("table", class_="calendar__table")
        if not table:
            return events

        rows = table.find_all("tr", class_=lambda x: x and "calendar__row" in x)

        current_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        for row in rows:
            try:
                # Date row
                if "calendar__row--day-breaker" in (row.get("class") or []):
                    date_str = row.get_text(strip=True)
                    parsed_date = self._parse_date_header(date_str)
                    if parsed_date:
                        current_date = parsed_date
                    continue

                # Event row
                time_td = row.find("td", class_="calendar__time")
                currency_td = row.find("td", class_="calendar__currency")
                impact_td = row.find("td", class_="calendar__impact")
                event_td = row.find("td", class_="calendar__event")
                actual_td = row.find("td", class_="calendar__actual")
                forecast_td = row.find("td", class_="calendar__forecast")
                previous_td = row.find("td", class_="calendar__previous")

                if not event_td:
                    continue

                # Parse time
                event_time = self._parse_event_time(time_td, current_date) if time_td else current_date

                # Parse currency
                currency = currency_td.get_text(strip=True) if currency_td else "USD"

                # Parse impact
                impact = self._parse_impact(impact_td)

                # Skip non-USD events that don't affect gold
                if currency not in {"USD", "ALL", "XAU"}:
                    continue

                event_name = event_td.get_text(strip=True)

                # Clean up event name
                event_name = re.sub(r"\s+", " ", event_name)

                actual = actual_td.get_text(strip=True) if actual_td else None
                forecast = forecast_td.get_text(strip=True) if forecast_td else None
                previous = previous_td.get_text(strip=True) if previous_td else None

                # Filter for high-impact events relevant to gold
                if impact == "HIGH" or self._is_gold_relevant(event_name):
                    events.append(CalendarEvent(
                        name=event_name,
                        currency=currency,
                        impact=impact,
                        datetime=event_time,
                        forecast=forecast,
                        previous=previous,
                        actual=actual,
                        source="forexfactory",
                    ))

            except Exception:
                continue

        return events

    def _parse_date_header(self, text: str) -> datetime | None:
        """Parse date header like 'Sun Dec 15' into datetime."""
        try:
            # Remove day name
            text = re.sub(r"^[A-Za-z]{3}\s+", "", text)
            current_year = datetime.now().year
            parsed = datetime.strptime(f"{text} {current_year}", "%b %d %Y")
            return parsed
        except ValueError:
            return None

    def _parse_event_time(self, time_td, base_date: datetime) -> datetime:
        """Parse event time from table cell."""
        time_str = time_td.get_text(strip=True)
        try:
            # Handle formats like "8:30am", "1:45pm", " Tentative"
            time_str = time_str.replace("Tentative", "").strip()
            if not time_str:
                return base_date

            # Try 12-hour format
            parsed_time = datetime.strptime(time_str, "%I:%M%p").time()
            return base_date.replace(hour=parsed_time.hour, minute=parsed_time.minute)
        except ValueError:
            try:
                parsed_time = datetime.strptime(time_str, "%H:%M").time()
                return base_date.replace(hour=parsed_time.hour, minute=parsed_time.minute)
            except ValueError:
                return base_date

    def _parse_impact(self, impact_td) -> EventImpact:
        """Parse impact level from icon span."""
        if not impact_td:
            return "LOW"

        span = impact_td.find("span", class_=lambda x: x and "icon--impact" in x)
        if not span:
            return "LOW"

        impact_class = span.get("class", [])
        if any("high" in c.lower() for c in impact_class):
            return "HIGH"
        elif any("medium" in c.lower() for c in impact_class):
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _is_gold_relevant(event_name: str) -> bool:
        """Check if event is relevant to XAU/USD."""
        gold_keywords = [
            "non-farm", "nfp", "cpi", "inflation", "fed", "fomc", "interest rate",
            "gdp", "retail sales", "pmi", "unemployment", "jobless", "adp",
            "treasury", "bond", "yield", "dollar", "dxy", "powell",
            "geopolitical", "war", "conflict", "crisis",
        ]
        name_lower = event_name.lower()
        return any(kw in name_lower for kw in gold_keywords)


class InvestingScraper:
    """Scraper for Investing.com economic calendar."""

    BASE_URL = "https://www.investing.com/economic-calendar/"
    API_URL = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            **HEADERS,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.investing.com/economic-calendar/",
        })

    def fetch_today(self) -> list[CalendarEvent]:
        """Fetch today's events from Investing.com."""
        try:
            # First get the page to establish session
            self.session.get(self.BASE_URL, timeout=self.timeout)

            today = datetime.now()
            payload = {
                "dateFrom": today.strftime("%Y-%m-%d"),
                "dateTo": today.strftime("%Y-%m-%d"),
                "timeZone": "55",  # UTC
                "sortDirection": "asc",
                "country[]": "5",  # United States
                "importance[]": "3",  # High impact only
            }

            response = self.session.post(self.API_URL, data=payload, timeout=self.timeout)
            response.raise_for_status()
            return self._parse_json(response.json())
        except Exception as e:
            raise RuntimeError(f"Investing.com fetch failed: {e}")

    def _parse_json(self, data: dict) -> list[CalendarEvent]:
        """Parse Investing.com JSON response."""
        events: list[CalendarEvent] = []

        if not isinstance(data, dict) or "data" not in data:
            return events

        html_content = data.get("data", "")
        soup = BeautifulSoup(html_content, "lxml")
        rows = soup.find_all("tr")

        for row in rows:
            try:
                tds = row.find_all("td")
                if len(tds) < 5:
                    continue

                # Time
                time_text = tds[0].get_text(strip=True)
                event_time = self._parse_time(time_text)

                # Currency/Country
                currency = tds[1].get_text(strip=True)

                # Impact
                impact_img = tds[2].find("i", class_=lambda x: x and "grayFullBullish" in x)
                impact = self._parse_investing_impact(impact_img)

                # Event name
                event_name = tds[3].get_text(strip=True)
                event_name = re.sub(r"\s+", " ", event_name)

                # Actual, Forecast, Previous
                actual = tds[4].get_text(strip=True) if len(tds) > 4 else None
                forecast = tds[5].get_text(strip=True) if len(tds) > 5 else None
                previous = tds[6].get_text(strip=True) if len(tds) > 6 else None

                if impact == "HIGH" or ForexFactoryScraper._is_gold_relevant(event_name):
                    events.append(CalendarEvent(
                        name=event_name,
                        currency=currency,
                        impact=impact,
                        datetime=event_time,
                        forecast=forecast,
                        previous=previous,
                        actual=actual,
                        source="investing",
                    ))

            except Exception:
                continue

        return events

    def _parse_time(self, time_str: str) -> datetime:
        """Parse time string."""
        base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            parsed = datetime.strptime(time_str, "%H:%M").time()
            return base.replace(hour=parsed.hour, minute=parsed.minute)
        except ValueError:
            return base

    def _parse_investing_impact(self, impact_element) -> EventImpact:
        """Parse impact from Investing.com bull icons."""
        if not impact_element:
            return "LOW"

        classes = impact_element.get("class", [])
        class_str = " ".join(classes)

        # Count grayFullBullish icons
        bull_count = class_str.count("grayFullBullish")
        if bull_count >= 3:
            return "HIGH"
        elif bull_count == 2:
            return "MEDIUM"
        return "LOW"
