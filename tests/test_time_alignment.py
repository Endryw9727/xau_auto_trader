import pandas as pd

from src.utils.time_alignment import latest_closed_from_index, to_utc_timestamp


def test_mt5_naive_europe_rome_timestamp_diventa_utc_cest():
    result = to_utc_timestamp("2026-06-02 23:45:00", source_timezone="Europe/Rome")

    assert result == pd.Timestamp("2026-06-02 21:45:00", tz="UTC")


def test_timestamp_utc_aware_non_viene_convertito_due_volte():
    source = pd.Timestamp("2026-06-02 23:45:00", tz="UTC")

    result = to_utc_timestamp(source, source_timezone="Europe/Rome")

    assert result == source


def test_latest_closed_candle_non_usa_candela_corrente_aperta():
    index = pd.DatetimeIndex(
        [
            pd.Timestamp("2026-06-02 23:30:00"),
            pd.Timestamp("2026-06-02 23:45:00"),
            pd.Timestamp("2026-06-03 00:00:00"),
        ]
    )

    result = latest_closed_from_index(
        index,
        source_timezone="Europe/Rome",
        now=pd.Timestamp("2026-06-02 22:06:00", tz="UTC"),
        timeframe_minutes=15,
    )

    assert result == pd.Timestamp("2026-06-02 21:45:00", tz="UTC")
