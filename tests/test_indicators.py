import pandas as pd
import pytest

from src.strategy.indicators import (
    add_adx,
    add_all_core_indicators,
    add_atr,
    add_ema,
    add_macd,
    add_rsi,
)


def make_test_ohlcv_data(rows: int = 60) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01 09:00:00", periods=rows, freq="min")

    data = {
        "Open": [100 + i * 0.1 for i in range(rows)],
        "High": [101 + i * 0.1 for i in range(rows)],
        "Low": [99 + i * 0.1 for i in range(rows)],
        "Close": [100.5 + i * 0.1 for i in range(rows)],
        "Volume": [1000 + i for i in range(rows)],
    }

    return pd.DataFrame(data, index=dates)


def test_add_ema():
    df = make_test_ohlcv_data()
    result = add_ema(df, 20)

    assert "EMA_20" in result.columns
    assert len(result) == len(df)
    assert "EMA_20" not in df.columns


def test_add_rsi():
    df = make_test_ohlcv_data()
    result = add_rsi(df, 14)

    assert "RSI_14" in result.columns
    assert len(result) == len(df)


def test_add_atr():
    df = make_test_ohlcv_data()
    result = add_atr(df, 14)

    assert "ATR_14" in result.columns
    assert len(result) == len(df)
    assert result["ATR_14"].dropna().iloc[-1] > 0


def test_add_macd():
    df = make_test_ohlcv_data()
    result = add_macd(df)

    assert "MACD" in result.columns
    assert "MACD_SIGNAL" in result.columns
    assert "MACD_HIST" in result.columns
    assert len(result) == len(df)


def test_add_adx():
    df = make_test_ohlcv_data()
    result = add_adx(df, 14)

    assert "PLUS_DI_14" in result.columns
    assert "MINUS_DI_14" in result.columns
    assert "ADX_14" in result.columns
    assert len(result) == len(df)


def test_add_all_core_indicators():
    df = make_test_ohlcv_data()
    result = add_all_core_indicators(df)

    expected_columns = [
        "EMA_20",
        "EMA_50",
        "EMA_200",
        "RSI_14",
        "ATR_14",
        "MACD",
        "MACD_SIGNAL",
        "MACD_HIST",
        "PLUS_DI_14",
        "MINUS_DI_14",
        "ADX_14",
    ]

    for column in expected_columns:
        assert column in result.columns


def test_invalid_period_raises_error():
    df = make_test_ohlcv_data()

    with pytest.raises(ValueError):
        add_ema(df, 0)


def test_missing_column_raises_error():
    df = pd.DataFrame({"Open": [1, 2, 3]})

    with pytest.raises(ValueError):
        add_rsi(df)
