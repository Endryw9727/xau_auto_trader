import numpy as np
import pandas as pd

from src.strategy.rules import StrategyConfig
from src.strategy_lab import strategy_v50_pine
from src.strategy_lab.v50_mtf_features import build_v50_mtf_dataset


def make_timeframe_frame(timeframe: str, start: str, periods: int, freq: str, base: float) -> pd.DataFrame:
    times = pd.date_range(start, periods=periods, freq=freq)
    close = [base + index * 0.5 + np.sin(index / 4) * 0.1 for index in range(periods)]

    return pd.DataFrame(
        {
            "time": times,
            "open": [value - 0.1 for value in close],
            "high": [value + 0.5 for value in close],
            "low": [value - 0.5 for value in close],
            "close": close,
            "volume": [1.0] * periods,
            "timeframe": [timeframe] * periods,
            "has_real_volume": [False] * periods,
        }
    )


def make_mtf_inputs() -> dict[str, pd.DataFrame]:
    return {
        "M5": make_timeframe_frame("M5", "2026-01-01 00:00:00", 120, "5min", 100.0),
        "M15": make_timeframe_frame("M15", "2026-01-01 00:00:00", 80, "15min", 100.0),
        "H1": make_timeframe_frame("H1", "2026-01-01 00:00:00", 20, "1h", 100.0),
        "H4": make_timeframe_frame("H4", "2026-01-01 00:00:00", 12, "4h", 100.0),
    }


def test_build_v50_mtf_dataset_generates_m10_from_m5():
    dataset = build_v50_mtf_dataset(make_mtf_inputs())

    assert len(dataset) > 0
    assert "close_10" in dataset.columns
    assert "ema21_10" in dataset.columns
    assert dataset["timeframe"].eq("M5").all()


def test_build_v50_mtf_dataset_has_main_columns():
    dataset = build_v50_mtf_dataset(make_mtf_inputs())
    expected_columns = {
        "time",
        "open",
        "high",
        "low",
        "close",
        "ema21",
        "ema50",
        "ema200",
        "ema50_slope",
        "rsi",
        "williams_r",
        "plus_di",
        "minus_di",
        "adx",
        "atr",
        "candle_body",
        "candle_range",
        "body_to_range_ratio",
        "distance_from_ema20",
        "distance_from_ema50",
        "session",
        "ema21_15",
        "ema50_1h",
        "ema200_4h",
    }

    assert expected_columns.issubset(dataset.columns)


def test_build_v50_mtf_dataset_shifts_higher_timeframes_before_merge():
    inputs = make_mtf_inputs()
    inputs["H1"].loc[inputs["H1"].index, "close"] = [1000 + index * 100 for index in range(len(inputs["H1"]))]

    dataset = build_v50_mtf_dataset(inputs)
    row_at_0100 = dataset[dataset["time"] == pd.Timestamp("2026-01-01 01:00:00")].iloc[0]
    row_at_0200 = dataset[dataset["time"] == pd.Timestamp("2026-01-01 02:00:00")].iloc[0]

    assert row_at_0100["close_1h"] == 1000
    assert row_at_0200["close_1h"] == 1100


def test_generate_mtf_signal_returns_supported_side():
    dataset = build_v50_mtf_dataset(make_mtf_inputs())

    signal = strategy_v50_pine.generate_mtf_signal(dataset, StrategyConfig(timeframe="5m"))

    assert signal.side in {"BUY", "SELL", "NO_TRADE"}


def test_v50_mtf_research_only_without_live_or_api_references():
    checked_files = [
        "src/strategy_lab/v50_mtf_features.py",
        "src/strategy_lab/strategy_v50_pine.py",
        "scripts/run_v50_mtf_lab.py",
    ]

    for path in checked_files:
        source = open(path, encoding="utf-8").read()
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source

