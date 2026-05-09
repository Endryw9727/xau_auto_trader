from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.features.feature_engine import build_features


def make_feature_data(rows: int = 260) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01 00:00:00", periods=rows, freq="15min")
    price = 2350.0
    close = []

    for i in range(rows):
        if i < 120:
            price += 0.20
        elif i < 190:
            price -= 0.12
        else:
            price += 0.08

        close.append(price)

    return pd.DataFrame(
        {
            "Open": [value - 0.2 for value in close],
            "High": [value + 0.8 for value in close],
            "Low": [value - 0.8 for value in close],
            "Close": close,
            "Volume": [1000] * rows,
        },
        index=dates,
    )


def test_build_features_returns_dataframe_and_preserves_rows():
    data = make_feature_data()

    features = build_features(data)

    assert isinstance(features, pd.DataFrame)
    assert len(features) == len(data)
    assert features.index.equals(data.index)


def test_build_features_creates_main_columns():
    features = build_features(make_feature_data())

    expected_columns = {
        "ema_20",
        "ema_50",
        "ema_200",
        "ema_20_slope",
        "ema_50_slope",
        "rsi",
        "adx",
        "atr",
        "atr_ratio",
        "williams_r",
        "candle_body",
        "candle_range",
        "body_to_range_ratio",
        "upper_wick_ratio",
        "lower_wick_ratio",
        "distance_from_ema20",
        "distance_from_ema50",
        "session",
        "hour",
        "day_of_week",
        "trend_regime",
        "volatility_regime",
        "candle_regime",
    }

    assert expected_columns.issubset(set(features.columns))


def test_build_features_does_not_produce_infinite_values():
    features = build_features(make_feature_data())
    numeric_features = features.select_dtypes(include="number")

    assert not np.isinf(numeric_features.to_numpy()).any()


def test_build_features_regime_columns_exist_and_are_classified():
    features = build_features(make_feature_data())

    assert "trend_regime" in features.columns
    assert "volatility_regime" in features.columns
    assert set(features["trend_regime"].dropna().unique()).issubset({"bullish", "bearish", "neutral"})
    assert set(features["volatility_regime"].dropna().unique()).issubset({"low", "normal", "high"})
    assert set(features["candle_regime"].dropna().unique()).issubset({"impulse", "normal", "indecision"})


def test_build_features_rejects_missing_ohlcv_columns():
    data = make_feature_data().drop(columns=["Volume"])

    with pytest.raises(ValueError):
        build_features(data)


def test_feature_engine_is_research_only_without_live_or_api_references():
    checked_files = [
        Path("src/features/feature_engine.py"),
        Path("scripts/analyze_features.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
