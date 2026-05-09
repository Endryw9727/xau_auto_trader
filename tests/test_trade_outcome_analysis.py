from pathlib import Path

import pandas as pd

from src.analysis.trade_outcome_analysis import analyze_trade_outcomes, build_trade_feature_dataset
from src.features.feature_engine import build_features


def make_market_data(rows: int = 80) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01 00:00:00", periods=rows, freq="15min")
    price = 2350.0
    close = []

    for i in range(rows):
        if i < 35:
            price += 0.25
        elif i < 60:
            price -= 0.15
        else:
            price += 0.10

        close.append(price)

    return pd.DataFrame(
        {
            "Open": [value - 0.2 for value in close],
            "High": [value + 0.9 for value in close],
            "Low": [value - 0.9 for value in close],
            "Close": close,
            "Volume": [1000] * rows,
        },
        index=dates,
    )


def make_trades() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp_open": "2026-01-01 03:01:00",
                "timestamp_close": "2026-01-01 03:30:00",
                "side": "BUY",
                "entry_price": 2355.0,
                "profit_loss": 12.0,
                "result": "WIN",
            },
            {
                "timestamp_open": "2026-01-01 10:59:00",
                "timestamp_close": "2026-01-01 11:30:00",
                "side": "SELL",
                "entry_price": 2352.0,
                "profit_loss": -5.0,
                "result": "LOSS",
            },
            {
                "timestamp_open": "2026-01-01 15:02:00",
                "timestamp_close": "2026-01-01 15:45:00",
                "side": "BUY",
                "entry_price": 2358.0,
                "profit_loss": 7.0,
                "result": "WIN",
            },
        ]
    )


def test_trade_feature_join_uses_nearest_feature_timestamp():
    features = build_features(make_market_data())
    trades = make_trades()

    enriched = build_trade_feature_dataset(trades, features)

    assert len(enriched) == len(trades)
    assert "feature_timestamp" in enriched.columns
    assert pd.Timestamp(enriched.loc[0, "feature_timestamp"]) == pd.Timestamp("2026-01-01 03:00:00")


def test_analyze_trade_outcomes_returns_non_empty_outputs():
    features = build_features(make_market_data())
    trades = make_trades()

    results = analyze_trade_outcomes(trades, features)

    assert not results["trade_feature_dataset"].empty
    assert not results["outcome_by_session"].empty
    assert not results["outcome_by_trend_regime"].empty


def test_trade_feature_dataset_has_trade_and_feature_columns():
    features = build_features(make_market_data())
    trades = make_trades()

    results = analyze_trade_outcomes(trades, features)
    dataset = results["trade_feature_dataset"]

    expected_columns = {
        "timestamp_open",
        "side",
        "profit_loss",
        "feature_timestamp",
        "session",
        "trend_regime",
        "volatility_regime",
        "candle_regime",
        "adx",
        "rsi",
        "williams_r",
        "distance_from_ema20",
        "atr_ratio",
    }

    assert expected_columns.issubset(set(dataset.columns))


def test_outcome_groupings_include_trade_count_and_net_profit():
    features = build_features(make_market_data())
    trades = make_trades()

    results = analyze_trade_outcomes(trades, features)

    for key in ["outcome_by_session", "outcome_by_adx_bucket", "outcome_by_rsi_bucket"]:
        summary = results[key]

        assert "total_trades" in summary.columns
        assert "net_profit" in summary.columns
        assert int(summary["total_trades"].sum()) == len(trades)


def test_trade_outcome_analysis_is_research_only_without_live_or_api_references():
    checked_files = [
        Path("src/analysis/trade_outcome_analysis.py"),
        Path("scripts/analyze_trade_outcomes.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
