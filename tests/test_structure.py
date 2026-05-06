import pandas as pd
import pytest

from src.strategy.structure import (
    add_swing_points,
    detect_break_of_structure,
    detect_trend_from_swings,
    get_latest_swing_highs,
    get_latest_swing_lows,
    summarize_market_structure,
)


def make_structure_test_data() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01 09:00:00", periods=11, freq="min")

    return pd.DataFrame(
        {
            "Open":  [100, 101, 102, 101, 100, 102, 104, 103, 102, 105, 107],
            "High":  [101, 103, 105, 103, 102, 104, 107, 105, 104, 108, 110],
            "Low":   [99, 100, 101, 99, 98, 101, 103, 101, 100, 104, 106],
            "Close": [100, 102, 104, 100, 101, 103, 106, 102, 103, 107, 109],
            "Volume": [1000] * 11,
        },
        index=dates,
    )


def make_bearish_structure_test_data() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01 09:00:00", periods=11, freq="min")

    return pd.DataFrame(
        {
            "Open":  [110, 109, 108, 109, 110, 108, 106, 107, 108, 105, 103],
            "High":  [111, 110, 109, 111, 112, 109, 107, 109, 110, 106, 104],
            "Low":   [109, 107, 105, 107, 108, 105, 102, 104, 105, 101, 99],
            "Close": [110, 108, 106, 110, 109, 106, 103, 108, 106, 102, 100],
            "Volume": [1000] * 11,
        },
        index=dates,
    )


def test_add_swing_points_creates_columns():
    df = make_structure_test_data()

    result = add_swing_points(df, lookback=1)

    assert "SWING_HIGH" in result.columns
    assert "SWING_LOW" in result.columns
    assert result["SWING_HIGH"].dtype == bool
    assert result["SWING_LOW"].dtype == bool


def test_get_latest_swing_highs_and_lows():
    df = make_structure_test_data()
    structured = add_swing_points(df, lookback=1)

    highs = get_latest_swing_highs(structured, count=2)
    lows = get_latest_swing_lows(structured, count=2)

    assert isinstance(highs, list)
    assert isinstance(lows, list)
    assert len(highs) <= 2
    assert len(lows) <= 2


def test_detect_trend_returns_valid_state():
    df = make_structure_test_data()
    structured = add_swing_points(df, lookback=1)

    trend = detect_trend_from_swings(structured)

    assert trend in {"BULLISH", "BEARISH", "RANGE", "UNKNOWN"}


def test_detect_break_of_structure_returns_valid_event():
    df = make_structure_test_data()
    structured = add_swing_points(df, lookback=1)

    event = detect_break_of_structure(structured, previous_trend="UNKNOWN")

    assert event in {"BOS_BULLISH", "BOS_BEARISH", "CHOCH_BULLISH", "CHOCH_BEARISH", "NONE"}


def test_summarize_market_structure():
    df = make_structure_test_data()

    summary = summarize_market_structure(df, lookback=1)

    assert summary.trend in {"BULLISH", "BEARISH", "RANGE", "UNKNOWN"}
    assert summary.event in {"BOS_BULLISH", "BOS_BEARISH", "CHOCH_BULLISH", "CHOCH_BEARISH", "NONE"}


def test_invalid_lookback_raises_error():
    df = make_structure_test_data()

    with pytest.raises(ValueError):
        add_swing_points(df, lookback=0)


def test_missing_columns_raises_error():
    df = pd.DataFrame({"Close": [1, 2, 3]})

    with pytest.raises(ValueError):
        add_swing_points(df, lookback=1)
