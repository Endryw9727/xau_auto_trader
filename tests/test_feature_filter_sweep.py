from pathlib import Path

import pandas as pd

from scripts.run_feature_filter_sweep import parse_args
from src.backtesting.backtester import BacktestConfig
from src.strategy.rules import StrategyConfig
from src.strategy_lab.feature_filter_sweep import (
    SWEEP_COLUMNS,
    build_focused_feature_filter_variants,
    build_feature_filter_variants,
    filter_fallback_sweep_results,
    filter_primary_sweep_results,
    run_feature_filter_sweep,
)


def make_sweep_data(rows: int = 140) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01 00:00:00", periods=rows, freq="15min")
    price = 2350.0
    close = []

    for index in range(rows):
        if index < rows // 2:
            price += 0.25
        else:
            price -= 0.18
        close.append(price)

    return pd.DataFrame(
        {
            "Open": [value - 0.1 for value in close],
            "High": [value + 1.2 for value in close],
            "Low": [value - 1.2 for value in close],
            "Close": close,
            "Volume": [1000] * rows,
        },
        index=dates,
    )


def test_feature_filter_sweep_builds_expected_variant_grid():
    variants = build_feature_filter_variants()

    assert len(variants) == 2 * 4 * 7 * 2 * 3 * 3
    assert any(variant.allowed_sessions_label == "All" for variant in variants)
    assert any(variant.candle_filter == "normal + indecision" for variant in variants)
    assert any(variant.adx_filter == "moderate + strong + very_strong" for variant in variants)


def test_feature_filter_sweep_variant_names_are_unique():
    variants = build_feature_filter_variants()
    variant_names = [variant.variant_name for variant in variants]

    assert len(variant_names) == len(set(variant_names))


def test_focused_feature_filter_sweep_builds_fewer_unique_variants():
    full_variants = build_feature_filter_variants()
    focused_variants = build_focused_feature_filter_variants()
    focused_names = [variant.variant_name for variant in focused_variants]

    assert len(focused_variants) < len(full_variants)
    assert len(focused_names) == len(set(focused_names))
    assert len(focused_variants) == 2 * 3 * 5 * 2 * 2 * 1
    assert all(variant.trend_filter == "bullish + bearish only" for variant in focused_variants)
    assert all(variant.allowed_sessions_label not in {"Asia", "New York"} for variant in focused_variants)
    assert all(variant.adx_filter != "moderate only" for variant in focused_variants)


def test_feature_filter_sweep_output_contains_required_columns(tmp_path):
    variants = build_feature_filter_variants()[:2]
    output_path = tmp_path / "feature_filter_sweep.csv"

    comparison = run_feature_filter_sweep(
        df=make_sweep_data(),
        strategy_config=StrategyConfig(),
        backtest_config=BacktestConfig(warmup_candles=60, allowed_sessions=None),
        variants=variants,
        output_path=output_path,
    )

    assert output_path.exists()
    assert list(comparison.columns) == SWEEP_COLUMNS
    assert len(comparison) == len(variants)
    assert {"variant_name", "total_trades", "net_profit", "profit_factor"}.issubset(comparison.columns)


def test_feature_filter_sweep_cli_options():
    full_args = parse_args(["--full"])
    focused_args = parse_args(["--focused"])
    candle_args = parse_args(["--candles", "20000"])

    assert full_args.full is True
    assert focused_args.focused is True
    assert candle_args.candles == 20000


def test_feature_filter_sweep_result_filters():
    comparison = pd.DataFrame(
        [
            {"total_trades": 120, "net_profit": 10.0, "max_drawdown": 5.0},
            {"total_trades": 120, "net_profit": -1.0, "max_drawdown": 5.0},
            {"total_trades": 60, "net_profit": 1.0, "max_drawdown": 2.0},
        ]
    )

    primary = filter_primary_sweep_results(comparison)
    fallback = filter_fallback_sweep_results(comparison)

    assert len(primary) == 1
    assert len(fallback) == 3


def test_feature_filter_sweep_research_only_without_live_or_api_references():
    checked_files = [
        Path("scripts/run_feature_filter_sweep.py"),
        Path("src/strategy_lab/feature_filter_sweep.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
