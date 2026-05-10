from pathlib import Path

import pandas as pd

from src.backtesting.backtester import BacktestConfig
from src.strategy.rules import StrategyConfig
from src.strategy_lab.lab import get_default_strategy_specs
from src.strategy_lab.strategy_v5 import STRATEGY_NAME as FEATURE_FILTERED_NAME
from src.strategy_lab.strategy_v6 import STRATEGY_NAME as RELAXED_OFFASIA_NAME
from src.strategy_lab.strategy_v50_candidates import OFFICIAL_CANDIDATE_STRATEGY_NAMES
from src.strategy_lab.strategy_v50_pine import MTF_STRATEGY_NAME, STRATEGY_NAME as V50_TECHNICAL_NAME
from src.strategy_lab.v50_mtf_features import build_v50_mtf_dataset
from src.strategy_lab.walk_forward_analysis import (
    WALK_FORWARD_COLUMNS,
    get_walk_forward_strategy_specs,
    run_walk_forward_analysis,
    split_into_periods,
    summarize_walk_forward_results,
)


def make_walk_forward_data(rows: int = 900) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01 00:00:00", periods=rows, freq="12h")
    price = 2350.0
    close = []

    for index in range(rows):
        if index < rows // 3:
            price += 0.35
        elif index < rows * 2 // 3:
            price -= 0.22
        else:
            price += 0.18
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


def make_timeframe_frame(timeframe: str, start: str, periods: int, freq: str, base: float) -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq=freq)
    close = [base + index * 0.15 for index in range(periods)]

    return pd.DataFrame(
        {
            "time": dates,
            "open": [value - 0.1 for value in close],
            "high": [value + 0.8 for value in close],
            "low": [value - 0.8 for value in close],
            "close": close,
            "volume": [1.0] * periods,
            "timeframe": [timeframe] * periods,
            "has_real_volume": [False] * periods,
        }
    )


def make_mtf_walk_forward_data() -> pd.DataFrame:
    timeframes = {
        "M5": make_timeframe_frame("M5", "2025-01-01 00:00:00", 600, "5min", 2350.0),
        "M15": make_timeframe_frame("M15", "2025-01-01 00:00:00", 240, "15min", 2350.0),
        "H1": make_timeframe_frame("H1", "2025-01-01 00:00:00", 80, "1h", 2350.0),
        "H4": make_timeframe_frame("H4", "2025-01-01 00:00:00", 40, "4h", 2350.0),
    }

    return build_v50_mtf_dataset(timeframes)


def test_split_into_periods_yearly_half_quarter_and_month():
    dates = pd.to_datetime(
        [
            "2025-01-01",
            "2025-04-01",
            "2025-07-01",
            "2025-10-01",
            "2026-01-01",
        ]
    )
    df = pd.DataFrame({"Close": range(len(dates))}, index=dates)

    yearly = split_into_periods(df, "yearly")
    half = split_into_periods(df, "half")
    quarter = split_into_periods(df, "quarter")
    month = split_into_periods(df, "month")

    assert len(yearly) == 2
    assert len(half) == 3
    assert len(quarter) == 5
    assert len(month) == 5
    assert yearly[0].period_start == pd.Timestamp("2025-01-01")
    assert half[1].period_start == pd.Timestamp("2025-07-01")


def test_walk_forward_output_contains_required_columns_and_strategies(tmp_path):
    output_path = tmp_path / "walk_forward_analysis.csv"

    analysis = run_walk_forward_analysis(
        df=make_walk_forward_data(),
        period="yearly",
        strategy_config=StrategyConfig(),
        backtest_config=BacktestConfig(warmup_candles=40, allowed_sessions=None),
        output_path=output_path,
    )

    assert output_path.exists()
    assert list(analysis.columns) == WALK_FORWARD_COLUMNS
    assert {
        FEATURE_FILTERED_NAME,
        RELAXED_OFFASIA_NAME,
        V50_TECHNICAL_NAME,
        *OFFICIAL_CANDIDATE_STRATEGY_NAMES,
        MTF_STRATEGY_NAME,
    }.issubset(set(analysis["strategy_name"]))
    assert {"total_trades", "profit_factor", "net_profit", "max_drawdown"}.issubset(analysis.columns)


def test_walk_forward_summary_contains_strategy_level_metrics(tmp_path):
    analysis = run_walk_forward_analysis(
        df=make_walk_forward_data(),
        period="yearly",
        strategy_config=StrategyConfig(),
        backtest_config=BacktestConfig(warmup_candles=40, allowed_sessions=None),
        output_path=tmp_path / "walk_forward_analysis.csv",
    )

    summary = summarize_walk_forward_results(analysis)

    assert {FEATURE_FILTERED_NAME, RELAXED_OFFASIA_NAME, MTF_STRATEGY_NAME}.issubset(set(summary["strategy_name"]))
    assert "total_periods" in summary.columns
    assert "total_net_profit" in summary.columns
    assert "worst_period_drawdown" in summary.columns


def test_walk_forward_strategy_specs_include_best_current_candidates():
    names = {spec.name for spec in get_walk_forward_strategy_specs()}
    default_names = {spec.name for spec in get_default_strategy_specs()}

    assert names == default_names
    assert set(OFFICIAL_CANDIDATE_STRATEGY_NAMES).issubset(names)
    assert MTF_STRATEGY_NAME in names


def test_walk_forward_uses_prebuilt_v50_mtf_dataset(tmp_path):
    analysis = run_walk_forward_analysis(
        df=make_walk_forward_data(rows=120),
        period="yearly",
        strategy_config=StrategyConfig(),
        backtest_config=BacktestConfig(warmup_candles=40, allowed_sessions=None),
        strategy_datasets={MTF_STRATEGY_NAME: make_mtf_walk_forward_data()},
        output_path=tmp_path / "walk_forward_analysis.csv",
    )

    mtf_rows = analysis[analysis["strategy_name"] == MTF_STRATEGY_NAME]

    assert not mtf_rows.empty
    assert "total_trades" in mtf_rows.columns


def test_walk_forward_research_only_without_live_or_api_references():
    checked_files = [
        Path("scripts/run_walk_forward_analysis.py"),
        Path("src/strategy_lab/walk_forward_analysis.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
