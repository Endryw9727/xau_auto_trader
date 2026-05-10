import numpy as np
import pandas as pd

from src.strategy.rules import StrategyConfig
from src.strategy_lab import strategy_v50_pine
from src.strategy_lab.lab import get_default_strategy_specs


def make_v50_data(rows: int = 600) -> pd.DataFrame:
    index = pd.date_range("2026-01-01 00:00:00", periods=rows, freq="15min")
    base = 2350.0
    close = []

    for i in range(rows):
        wave = np.sin(i / 8.0) * 0.45
        drift = i * 0.04
        close.append(base + drift + wave)

    return pd.DataFrame(
        {
            "Open": [value - 0.15 for value in close],
            "High": [value + 0.80 for value in close],
            "Low": [value - 0.85 for value in close],
            "Close": close,
            "Volume": [1000 + (i % 20) * 5 for i in range(rows)],
        },
        index=index,
    )


def test_build_v50_features_preserves_rows_and_marks_15m_approximation():
    data = make_v50_data()

    features = strategy_v50_pine.build_v50_features(data)

    assert len(features) == len(data)
    assert features.index.equals(data.index)
    assert features["v50_approximation_mode"].iloc[-1] == "approximated_10m_5m"


def test_build_v50_features_creates_main_columns_without_infinities():
    features = strategy_v50_pine.build_v50_features(make_v50_data())
    expected_columns = {
        "v50_ema21",
        "v50_ema50",
        "v50_ema200",
        "v50_rsi",
        "v50_williams_r",
        "v50_plus_di",
        "v50_minus_di",
        "v50_adx",
        "v50_atr",
        "v50_4h_ema50",
        "v50_1h_ema50",
        "v50_15m_ema50",
        "v50_10m_ema50",
        "v50_5m_ema50",
        "v50_score_long",
        "v50_score_short",
        "v50_session",
    }

    assert expected_columns.issubset(features.columns)
    numeric = features.select_dtypes(include=["number"])
    assert not np.isinf(numeric.to_numpy()).any()


def test_generate_signal_returns_supported_side():
    signal = strategy_v50_pine.generate_signal(make_v50_data(), StrategyConfig())

    assert signal.side in {"BUY", "SELL", "NO_TRADE"}
    assert "V50 Pine technical approximation" in signal.reason


def test_v50_pine_candidate_is_in_strategy_lab():
    names = {spec.name for spec in get_default_strategy_specs()}

    assert strategy_v50_pine.STRATEGY_NAME in names


def test_v50_pine_research_only_without_live_or_api_references():
    source = open("src/strategy_lab/strategy_v50_pine.py", encoding="utf-8").read()

    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
    assert ".env" not in source
