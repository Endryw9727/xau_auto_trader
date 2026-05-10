from pathlib import Path

import pandas as pd

from scripts import analyze_v50_daily_coverage as daily_script
from src.strategy_lab.strategy_v50_candidates import FINAL_CANDIDATE_STRATEGY_NAMES
from src.strategy_lab.v50_daily_coverage import (
    DAILY_COVERAGE_COLUMNS,
    build_daily_breakdown,
    build_daily_coverage_report,
)


def make_trades() -> pd.DataFrame:
    rows = []
    for strategy_name in FINAL_CANDIDATE_STRATEGY_NAMES:
        rows.extend(
            [
                {
                    "strategy_name": strategy_name,
                    "entry_time": "2025-01-01 10:00:00",
                    "side": "BUY",
                    "pnl": 10.0,
                    "profit_loss": 10.0,
                    "bars_in_trade": 4,
                },
                {
                    "strategy_name": strategy_name,
                    "entry_time": "2025-01-03 11:00:00",
                    "side": "SELL",
                    "pnl": -5.0,
                    "profit_loss": -5.0,
                    "bars_in_trade": 2,
                },
                {
                    "strategy_name": strategy_name,
                    "entry_time": "2025-01-03 12:00:00",
                    "side": "SELL",
                    "pnl": -4.0,
                    "profit_loss": -4.0,
                    "bars_in_trade": 3,
                },
            ]
        )
    return pd.DataFrame(rows)


def make_market_data() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=4, freq="D")
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0, 103.0],
            "High": [104.0, 102.0, 108.0, 104.0],
            "Low": [99.0, 100.0, 101.0, 102.0],
            "Close": [103.0, 101.0, 106.0, 103.5],
            "Volume": [1.0] * 4,
        },
        index=dates,
    )


def test_daily_coverage_metrics_include_no_trade_days_and_columns():
    breakdown = build_daily_breakdown(make_trades(), market_data=make_market_data())
    coverage = build_daily_coverage_report(breakdown)

    balanced = coverage[coverage["strategy_name"] == "v50_final_balanced_strategy"].iloc[0]

    assert set(DAILY_COVERAGE_COLUMNS).issubset(coverage.columns)
    assert balanced["total_trading_days"] == 4
    assert balanced["active_trading_days"] == 2
    assert balanced["no_trade_days"] == 2
    assert balanced["average_trades_per_day"] == 0.75
    assert "volatility_sufficient" in breakdown.columns


def test_daily_coverage_script_runs_and_exports(monkeypatch, tmp_path, capsys):
    coverage_path = tmp_path / "v50_daily_coverage.csv"
    breakdown_path = tmp_path / "v50_daily_breakdown.csv"

    monkeypatch.setattr(daily_script, "DEFAULT_DAILY_COVERAGE_PATH", coverage_path)
    monkeypatch.setattr(daily_script, "DEFAULT_DAILY_BREAKDOWN_PATH", breakdown_path)
    monkeypatch.setattr(daily_script, "load_strategy_trade_report", lambda: make_trades())
    monkeypatch.setattr(daily_script, "_load_market_data", lambda: make_market_data())

    daily_script.main()
    output = capsys.readouterr().out

    assert coverage_path.exists()
    assert breakdown_path.exists()
    assert "V50 Daily Coverage" in output
    assert "No strategy was promoted automatically." in output


def test_daily_coverage_sources_are_research_only():
    checked_files = [
        Path("src/strategy_lab/v50_daily_coverage.py"),
        Path("scripts/analyze_v50_daily_coverage.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
