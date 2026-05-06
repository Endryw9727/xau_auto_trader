from pathlib import Path

import pandas as pd
import pytest

from src.data_feed.market_data import (
    get_latest_candles,
    load_csv_data,
    resample_ohlcv,
    save_processed_data,
    validate_ohlcv_columns,
)


def test_load_csv_data(tmp_path):
    csv_path = tmp_path / "xauusd_test.csv"
    csv_path.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2026-01-01 09:00:00,2350,2355,2348,2352,100\n"
        "2026-01-01 09:01:00,2352,2356,2350,2354,110\n"
    )

    df = load_csv_data(csv_path)

    assert len(df) == 2
    assert isinstance(df.index, pd.DatetimeIndex)
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df.iloc[0]["Open"] == 2350


def test_validate_ohlcv_columns_raises_error():
    df = pd.DataFrame({"Date": [], "Open": []})

    with pytest.raises(ValueError):
        validate_ohlcv_columns(df)


def test_resample_ohlcv():
    dates = pd.date_range("2026-01-01 09:00:00", periods=5, freq="min")
    df = pd.DataFrame(
        {
            "Open": [100, 101, 102, 103, 104],
            "High": [101, 102, 103, 104, 105],
            "Low": [99, 100, 101, 102, 103],
            "Close": [100.5, 101.5, 102.5, 103.5, 104.5],
            "Volume": [10, 20, 30, 40, 50],
        },
        index=dates,
    )

    resampled = resample_ohlcv(df, "5min")

    assert len(resampled) == 1
    assert resampled.iloc[0]["Open"] == 100
    assert resampled.iloc[0]["High"] == 105
    assert resampled.iloc[0]["Low"] == 99
    assert resampled.iloc[0]["Close"] == 104.5
    assert resampled.iloc[0]["Volume"] == 150


def test_get_latest_candles():
    dates = pd.date_range("2026-01-01", periods=10, freq="min")
    df = pd.DataFrame(
        {
            "Open": range(10),
            "High": range(10),
            "Low": range(10),
            "Close": range(10),
            "Volume": range(10),
        },
        index=dates,
    )

    latest = get_latest_candles(df, 3)

    assert len(latest) == 3
    assert latest.iloc[0]["Open"] == 7


def test_save_processed_data(tmp_path):
    dates = pd.date_range("2026-01-01", periods=2, freq="min")
    df = pd.DataFrame(
        {
            "Open": [1, 2],
            "High": [2, 3],
            "Low": [0, 1],
            "Close": [1.5, 2.5],
            "Volume": [100, 200],
        },
        index=dates,
    )

    output_path = tmp_path / "processed" / "xauusd.csv"

    save_processed_data(df, output_path)

    assert output_path.exists()
