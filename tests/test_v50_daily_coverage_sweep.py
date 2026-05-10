from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from scripts import analyze_v50_daily_selection as selection_script
from scripts import run_v50_daily_coverage_sweep as sweep_script
from src.backtesting.backtester import BacktestConfig, BacktestResult
from src.backtesting.metrics import calculate_metrics
from src.strategy.rules import StrategyConfig
from src.strategy_lab import v50_daily_coverage_sweep as sweep


def make_data(rows: int = 20) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=rows, freq="D")
    return pd.DataFrame(
        {
            "Open": [100.0 + index for index in range(rows)],
            "High": [103.0 + index for index in range(rows)],
            "Low": [99.0 + index for index in range(rows)],
            "Close": [102.0 + index for index in range(rows)],
            "Volume": [1.0] * rows,
        },
        index=dates,
    )


def make_result(strategy_name: str, pnl_values: list[float] | None = None) -> BacktestResult:
    if pnl_values is None:
        pnl_values = [10.0, -5.0, 8.0, -4.0, 12.0, 9.0, -5.0, 11.0]
    trades = pd.DataFrame(
        {
            "strategy_name": [strategy_name] * len(pnl_values),
            "entry_time": pd.date_range("2025-01-01", periods=len(pnl_values), freq="D"),
            "side": ["BUY" if index % 2 == 0 else "SELL" for index in range(len(pnl_values))],
            "pnl": pnl_values,
            "profit_loss": pnl_values,
        }
    )
    metrics = calculate_metrics(trades, initial_balance=1000.0)
    return BacktestResult(trades=trades, metrics=metrics, final_balance=1000.0 + metrics.net_profit)


def test_daily_coverage_variants_include_required_names():
    names = [variant.variant_name for variant in sweep.build_daily_coverage_variants()]

    assert names == list(sweep.DAILY_VARIANT_NAMES)


def test_run_daily_coverage_sweep_generates_columns(monkeypatch, tmp_path):
    def fake_run_variant(**kwargs):
        variant = kwargs["variant"]
        return make_result(variant.variant_name)

    output_path = tmp_path / "v50_daily_coverage_sweep.csv"
    monkeypatch.setattr(sweep, "run_daily_coverage_variant", fake_run_variant)

    report = sweep.run_v50_daily_coverage_sweep(
        df=make_data(),
        strategy_config=StrategyConfig(),
        backtest_config=BacktestConfig(warmup_candles=0),
        output_path=output_path,
    )
    exported = pd.read_csv(output_path)

    assert output_path.exists()
    assert set(exported["variant_name"]) == set(sweep.DAILY_VARIANT_NAMES)
    assert {"average_trades_per_day", "active_day_ratio", "anti_overfit_pass"}.issubset(report.columns)


def test_daily_coverage_sweep_script_runs(monkeypatch, tmp_path, capsys):
    output_path = tmp_path / "v50_daily_coverage_sweep.csv"
    raw_path = tmp_path / "xauusd.csv"
    raw_path.write_text("placeholder", encoding="utf-8")
    fake_settings = SimpleNamespace(
        trading=SimpleNamespace(symbol="XAUUSD", base_timeframe="15m", live_mode=False)
    )

    def fake_run_sweep(*, output_path, **_kwargs):
        report = pd.DataFrame(
            [
                {
                    "strategy_name": "v50_final_balanced_strategy",
                    "variant_name": "daily_base",
                    "total_trades": 800,
                    "total_trading_days": 700,
                    "active_trading_days": 650,
                    "no_trade_days": 50,
                    "active_day_ratio": 0.92,
                    "average_trades_per_day": 1.14,
                    "win_rate": 40.0,
                    "profit_factor": 1.2,
                    "net_profit": 100.0,
                    "max_drawdown": 50.0,
                    "expectancy": 0.12,
                    "profit_drawdown_ratio": 2.0,
                    "max_consecutive_losses": 8,
                    "positive_days": 320,
                    "negative_days": 280,
                    "removed_trade_pct": 0.0,
                    "active_years": 2,
                    "max_year_net_profit_share": 0.6,
                    "anti_overfit_pass": True,
                }
            ],
            columns=sweep.DAILY_SWEEP_COLUMNS,
        )
        report.to_csv(output_path, index=False)
        return report

    monkeypatch.setattr(sweep_script, "RAW_DATA_PATH", raw_path)
    monkeypatch.setattr(sweep_script, "DEFAULT_DAILY_COVERAGE_SWEEP_PATH", output_path)
    monkeypatch.setattr(sweep_script, "load_settings", lambda: fake_settings)
    monkeypatch.setattr(sweep_script, "load_csv_data", lambda _path: make_data())
    monkeypatch.setattr(sweep_script, "build_strategy_config", lambda _settings: StrategyConfig())
    monkeypatch.setattr(sweep_script, "build_backtest_config", lambda _settings: BacktestConfig(warmup_candles=0))
    monkeypatch.setattr(sweep_script, "run_v50_daily_coverage_sweep", fake_run_sweep)

    sweep_script.main()
    output = capsys.readouterr().out

    assert output_path.exists()
    assert "V50 Daily Coverage Sweep" in output
    assert "No variant was promoted automatically." in output


def test_daily_selection_helpers_find_thresholds():
    report = pd.DataFrame(
        [
            {
                "variant_name": "daily_base",
                "total_trades": 800,
                "average_trades_per_day": 0.9,
                "active_day_ratio": 0.8,
                "profit_factor": 1.2,
                "net_profit": 100.0,
                "max_drawdown": 50.0,
                "profit_drawdown_ratio": 2.0,
                "max_consecutive_losses": 8,
                "anti_overfit_pass": True,
            },
            {
                "variant_name": "daily_soft_score",
                "total_trades": 900,
                "average_trades_per_day": 1.1,
                "active_day_ratio": 0.9,
                "profit_factor": 1.26,
                "net_profit": 120.0,
                "max_drawdown": 45.0,
                "profit_drawdown_ratio": 2.6,
                "max_consecutive_losses": 7,
                "anti_overfit_pass": True,
            },
        ]
    )
    ranking = selection_script.prepare_daily_selection_ranking(report)

    assert selection_script.select_best_balanced_quality_coverage(ranking)["variant_name"] == "daily_soft_score"


def test_daily_coverage_sweep_sources_are_research_only():
    checked_files = [
        Path("src/strategy_lab/v50_daily_coverage_sweep.py"),
        Path("scripts/run_v50_daily_coverage_sweep.py"),
        Path("scripts/analyze_v50_daily_selection.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
