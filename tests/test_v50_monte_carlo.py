from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from scripts import run_v50_monte_carlo as monte_script
from src.backtesting.backtester import BacktestConfig, BacktestResult
from src.backtesting.metrics import BacktestMetrics
from src.strategy.rules import StrategyConfig
from src.strategy_lab import v50_monte_carlo as monte
from src.strategy_lab.strategy_v50_candidates import FINAL_CANDIDATE_STRATEGY_NAMES


def make_data(rows: int = 40) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01 00:00:00", periods=rows, freq="15min")
    close = [2350.0 + index * 0.2 for index in range(rows)]
    return pd.DataFrame(
        {
            "Open": [value - 0.1 for value in close],
            "High": [value + 0.8 for value in close],
            "Low": [value - 0.8 for value in close],
            "Close": close,
            "Volume": [1000] * rows,
        },
        index=dates,
    )


def make_result(strategy_name: str = "test_strategy") -> BacktestResult:
    trades = pd.DataFrame(
        {
            "strategy_name": [strategy_name] * 5,
            "profit_loss": [10.0, -5.0, 8.0, -4.0, 12.0],
            "pnl": [10.0, -5.0, 8.0, -4.0, 12.0],
        }
    )
    return BacktestResult(
        trades=trades,
        metrics=BacktestMetrics(
            total_trades=5,
            wins=3,
            losses=2,
            breakeven=0,
            win_rate=60.0,
            net_profit=21.0,
            profit_factor=30.0 / 9.0,
            average_win=10.0,
            average_loss=-4.5,
            expectancy=4.2,
            max_drawdown=5.0,
            max_consecutive_wins=1,
            max_consecutive_losses=1,
        ),
        final_balance=1021.0,
    )


def test_simulate_trade_reshuffles_returns_requested_iterations():
    final_profits, drawdowns = monte.simulate_trade_reshuffles(
        pnl=np.array([10.0, -5.0, 8.0, -4.0, 12.0]),
        initial_balance=1000.0,
        iterations=25,
        seed=7,
    )

    assert len(final_profits) == 25
    assert len(drawdowns) == 25
    assert set(final_profits) == {21.0}
    assert drawdowns.max() >= 0.0


def test_monte_carlo_summary_row_contains_required_metrics():
    row = monte.monte_carlo_summary_row(
        strategy_name="test_strategy",
        pnl=np.array([10.0, -5.0, 8.0, -4.0, 12.0]),
        base_metrics={"net_profit": 21.0, "profit_factor": 3.0, "max_drawdown": 5.0},
        initial_balance=1000.0,
        iterations=25,
        seed=7,
    )

    assert row["strategy_name"] == "test_strategy"
    assert row["iterations"] == 25
    assert row["total_trades"] == 5
    assert "worst_5pct_drawdown" in row
    assert "probability_of_loss" in row


def test_run_v50_monte_carlo_generates_csv(monkeypatch, tmp_path):
    def fake_run_backtest(**kwargs):
        return make_result(kwargs["strategy_name"])

    output_path = tmp_path / "v50_monte_carlo.csv"
    monkeypatch.setattr(monte, "run_backtest", fake_run_backtest)

    report = monte.run_v50_monte_carlo(
        df=make_data(),
        strategy_config=StrategyConfig(),
        backtest_config=BacktestConfig(warmup_candles=0),
        iterations=25,
        output_path=output_path,
    )
    exported = pd.read_csv(output_path)

    assert output_path.exists()
    assert set(exported["strategy_name"]) == set(FINAL_CANDIDATE_STRATEGY_NAMES)
    assert {"worst_5pct_drawdown", "probability_drawdown_over_20_percent"}.issubset(report.columns)


def test_run_v50_monte_carlo_script_runs_without_live_or_api(monkeypatch, tmp_path, capsys):
    output_path = tmp_path / "v50_monte_carlo.csv"
    raw_path = tmp_path / "xauusd.csv"
    raw_path.write_text("placeholder", encoding="utf-8")
    fake_settings = SimpleNamespace(
        trading=SimpleNamespace(symbol="XAUUSD", base_timeframe="15m", live_mode=False)
    )

    def fake_run_monte(*, output_path, **_kwargs):
        report = pd.DataFrame(
            [
                {
                    "strategy_name": "v50_final_balanced_strategy",
                    "iterations": 25,
                    "total_trades": 5,
                    "base_net_profit": 21.0,
                    "base_profit_factor": 3.0,
                    "base_max_drawdown": 5.0,
                    "median_final_profit": 21.0,
                    "median_max_drawdown": 5.0,
                    "worst_5pct_drawdown": 6.0,
                    "worst_drawdown": 7.0,
                    "probability_of_loss": 0.0,
                    "probability_drawdown_over_20_percent": 0.0,
                }
            ],
            columns=monte.MONTE_CARLO_COLUMNS,
        )
        report.to_csv(output_path, index=False)
        return report

    monkeypatch.setattr(monte_script, "RAW_DATA_PATH", raw_path)
    monkeypatch.setattr(monte_script, "DEFAULT_V50_MONTE_CARLO_PATH", output_path)
    monkeypatch.setattr(monte_script, "MONTE_CARLO_ITERATIONS", 25)
    monkeypatch.setattr(monte_script, "load_settings", lambda: fake_settings)
    monkeypatch.setattr(monte_script, "load_csv_data", lambda _path: make_data())
    monkeypatch.setattr(monte_script, "build_strategy_config", lambda _settings: StrategyConfig())
    monkeypatch.setattr(monte_script, "build_backtest_config", lambda _settings: BacktestConfig(warmup_candles=0))
    monkeypatch.setattr(monte_script, "run_v50_monte_carlo", fake_run_monte)

    monte_script.main()
    output = capsys.readouterr().out

    assert output_path.exists()
    assert "V50 Monte Carlo" in output
    assert "No candidate was promoted automatically." in output


def test_v50_monte_carlo_sources_are_research_only():
    checked_files = [
        Path("src/strategy_lab/v50_monte_carlo.py"),
        Path("scripts/run_v50_monte_carlo.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
