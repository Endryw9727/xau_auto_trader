from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from scripts import run_v50_stress_test as stress_script
from src.backtesting.backtester import BacktestConfig, BacktestResult
from src.backtesting.metrics import BacktestMetrics
from src.strategy.rules import StrategyConfig
from src.strategy_lab import v50_stress_test as stress
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
            "entry_time": pd.date_range("2025-01-01", periods=5, freq="h"),
            "side": ["BUY", "SELL", "BUY", "SELL", "BUY"],
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


def test_v50_stress_scenarios_include_required_names():
    names = [scenario.name for scenario in stress.build_v50_stress_scenarios()]

    assert names == [
        "base",
        "spread_slippage_light",
        "spread_slippage_medium",
        "spread_slippage_heavy",
        "simulated_commission",
        "pnl_minus_10pct",
        "pnl_minus_20pct",
        "remove_best_5pct",
        "remove_best_10pct",
    ]


def test_apply_trade_stress_scales_and_removes_best_trades():
    result = make_result()
    scaled = stress.apply_trade_stress(
        result,
        stress.StressScenario("pnl_minus_20pct", pnl_multiplier=0.80),
        initial_balance=1000.0,
    )
    removed = stress.apply_trade_stress(
        result,
        stress.StressScenario("remove_best_10pct", remove_best_pct=0.10),
        initial_balance=1000.0,
    )

    assert scaled.metrics.net_profit == 16.8
    assert len(removed.trades) == 4
    assert removed.trades["profit_loss"].max() == 10.0


def test_run_v50_stress_test_generates_csv(monkeypatch, tmp_path):
    def fake_backtest(**kwargs):
        return make_result(kwargs["strategy_name"])

    output_path = tmp_path / "v50_stress_test.csv"
    monkeypatch.setattr(stress, "run_v50_candidate_backtest", fake_backtest)

    report = stress.run_v50_stress_test(
        df=make_data(),
        strategy_config=StrategyConfig(),
        backtest_config=BacktestConfig(warmup_candles=0),
        output_path=output_path,
    )
    exported = pd.read_csv(output_path)

    assert output_path.exists()
    assert set(exported["strategy_name"]) == set(FINAL_CANDIDATE_STRATEGY_NAMES)
    assert set(exported["scenario"]) == {scenario.name for scenario in stress.build_v50_stress_scenarios()}
    assert {"profit_drawdown_ratio", "max_consecutive_losses"}.issubset(report.columns)


def test_run_v50_stress_test_script_runs_without_live_or_api(monkeypatch, tmp_path, capsys):
    output_path = tmp_path / "v50_stress_test.csv"
    raw_path = tmp_path / "xauusd.csv"
    raw_path.write_text("placeholder", encoding="utf-8")
    fake_settings = SimpleNamespace(
        trading=SimpleNamespace(symbol="XAUUSD", base_timeframe="15m", live_mode=False)
    )

    def fake_run_stress(*, output_path, **_kwargs):
        report = pd.DataFrame(
            [
                {
                    "strategy_name": "v50_final_balanced_strategy",
                    "scenario": "base",
                    "total_trades": 1,
                    "wins": 1,
                    "losses": 0,
                    "win_rate": 100.0,
                    "profit_factor": 1.0,
                    "net_profit": 1.0,
                    "max_drawdown": 0.0,
                    "expectancy": 1.0,
                    "profit_drawdown_ratio": 0.0,
                    "max_consecutive_losses": 0,
                }
            ],
            columns=stress.STRESS_TEST_COLUMNS,
        )
        report.to_csv(output_path, index=False)
        return report

    monkeypatch.setattr(stress_script, "RAW_DATA_PATH", raw_path)
    monkeypatch.setattr(stress_script, "DEFAULT_V50_STRESS_TEST_PATH", output_path)
    monkeypatch.setattr(stress_script, "load_settings", lambda: fake_settings)
    monkeypatch.setattr(stress_script, "load_csv_data", lambda _path: make_data())
    monkeypatch.setattr(stress_script, "build_strategy_config", lambda _settings: StrategyConfig())
    monkeypatch.setattr(stress_script, "build_backtest_config", lambda _settings: BacktestConfig(warmup_candles=0))
    monkeypatch.setattr(stress_script, "run_v50_stress_test", fake_run_stress)

    stress_script.main()
    output = capsys.readouterr().out

    assert output_path.exists()
    assert "V50 Stress Test" in output
    assert "No candidate was promoted automatically." in output


def test_v50_stress_sources_are_research_only():
    checked_files = [
        Path("src/strategy_lab/v50_stress_test.py"),
        Path("scripts/run_v50_stress_test.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
