"""Central time-alignment helpers for MT5/VPS/V51 comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from zoneinfo import ZoneInfo

import pandas as pd


DEFAULT_MT5_TIMESTAMP_TIMEZONE = "Europe/Rome"


@dataclass(frozen=True)
class TimeAlignmentSnapshot:
    """Raw and UTC-normalized timestamp pair."""

    raw: str | None
    utc: pd.Timestamp | None
    source_timezone: str

    @property
    def utc_iso(self) -> str | None:
        return self.utc.isoformat() if self.utc is not None else None


def normalize_timezone_name(timezone: str | None) -> str:
    """Return a valid timezone name, falling back to the MT5 default."""
    name = timezone or DEFAULT_MT5_TIMESTAMP_TIMEZONE
    ZoneInfo(name)
    return name


def align_timestamp(value: object, *, source_timezone: str | None = None) -> TimeAlignmentSnapshot:
    """Return raw text and UTC-aware timestamp.

    Naive timestamps are interpreted as MT5/broker wall time in
    `source_timezone`. Already timezone-aware values are converted to UTC and
    are never localized a second time.
    """
    timezone = normalize_timezone_name(source_timezone)
    raw = raw_timestamp_text(value)
    utc = to_utc_timestamp(value, source_timezone=timezone)
    return TimeAlignmentSnapshot(raw=raw, utc=utc, source_timezone=timezone)


def to_utc_timestamp(value: object, *, source_timezone: str | None = None) -> pd.Timestamp | None:
    """Convert a timestamp-like value to UTC-aware pandas Timestamp."""
    if value is None:
        return None
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        return None
    if timestamp.tzinfo is not None:
        return timestamp.tz_convert(UTC)
    timezone = normalize_timezone_name(source_timezone)
    return timestamp.tz_localize(ZoneInfo(timezone)).tz_convert(UTC)


def to_utc_index(values: object, *, source_timezone: str | None = None) -> pd.DatetimeIndex:
    """Convert timestamp-like iterable/index to a UTC-aware DatetimeIndex."""
    parsed = pd.to_datetime(values, errors="coerce")
    aligned = [to_utc_timestamp(value, source_timezone=source_timezone) for value in parsed]
    return pd.DatetimeIndex([value for value in aligned if value is not None])


def now_utc(now: object | None = None, *, local_timezone: str | None = None) -> pd.Timestamp:
    """Return current or supplied time as UTC-aware Timestamp."""
    if now is None:
        return pd.Timestamp.now(tz=UTC)
    value = pd.Timestamp(now)
    if value.tzinfo is not None:
        return value.tz_convert(UTC)
    timezone = normalize_timezone_name(local_timezone)
    return value.tz_localize(ZoneInfo(timezone)).tz_convert(UTC)


def latest_closed_from_index(
    index: object,
    *,
    source_timezone: str | None = None,
    now: object | None = None,
    timeframe_minutes: float | int | None = None,
) -> pd.Timestamp:
    """Return the latest closed candle open time as UTC-aware timestamp.

    When `now` and `timeframe_minutes` are supplied, timestamps representing a
    still-open candle are excluded using open_time + timeframe <= now.
    """
    utc_index = to_utc_index(index, source_timezone=source_timezone).sort_values()
    if utc_index.empty:
        raise ValueError("No valid timestamps available")
    if now is None or not timeframe_minutes or float(timeframe_minutes) <= 0:
        return pd.Timestamp(utc_index[-1]).tz_convert(UTC)
    cutoff = now_utc(now, local_timezone=source_timezone) - pd.Timedelta(minutes=float(timeframe_minutes))
    closed = utc_index[utc_index <= cutoff]
    if closed.empty:
        raise ValueError("No closed candles available at the requested now/timeframe")
    return pd.Timestamp(closed[-1]).tz_convert(UTC)


def age_minutes(reference_utc: object, event_utc: object) -> float:
    """Return reference-event age in minutes after UTC normalization."""
    reference = to_utc_timestamp(reference_utc, source_timezone="UTC")
    event = to_utc_timestamp(event_utc, source_timezone="UTC")
    if reference is None or event is None:
        raise ValueError("Cannot calculate age for missing timestamps")
    return (reference - event).total_seconds() / 60.0


def raw_timestamp_text(value: object) -> str | None:
    """Return a stable raw timestamp representation for audit fields."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return pd.Timestamp(value).isoformat()
    except Exception:
        return str(value)
