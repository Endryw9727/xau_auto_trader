from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from scripts import analyze_v50_growth_refinement, run_v50_growth_refinement_sweep
from src.backtesting.backtester import BacktestConfig, BacktestResult
from src.backtesting.metrics import BacktestMetrics
from src.settings import load_yaml_config
from src.strategy.rules import StrategyConfig
from src.strategy.signals import TradingSignal
from src.strategy_lab import v50_growth_refinement_sweep as sweep
from src.strategy_lab import v50_edge_filters


def make_sweep_data(rows: int = 60) -> pd.DataFrame:
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


def make_trades(strategy_name: str, net_profit: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strategy_name": [strategy_name, strategy_name, strategy_name],
            "entry_time": ["2025-01-01 10:00:00", "2025-01-01 11:00:00", "2025-01-01 14:00:00"],
            "exit_time": ["2025-01-01 10:30:00", "2025-01-01 11:30:00", "2025-01-01 14:30:00"],
            "side": ["BUY", "SELL", "BUY"],
            "side_label": ["LONG", "SHORT", "LONG"],
            "session": ["LONDON", "LONDON", "NEW YORK"],
            "pnl": [net_profit, -1.0, 2.0],
            "profit_loss": [net_profit, -1.0, 2.0],
        }
    )


def make_result(total_trades: int, net_profit: float, strategy_name: str = "variant") -> BacktestResult:
    losses = total_trades // 2
    wins = total_trades - losses
    return BacktestResult(
        trades=make_trades(strategy_name, net_profit),
        metrics=BacktestMetrics(
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            breakeven=0,
            win_rate=wins / total_trades * 100 if total_trades else 0.0,
            net_profit=net_profit,
            profit_factor=1.2 if net_profit > 0 else 0.8 if total_trades else 0.0,
            average_win=2.0,
            average_loss=-1.0,
            expectancy=net_profit / total_trades if total_trades else 0.0,
            max_drawdown=10.0 if total_trades else 0.0,
            max_consecutive_wins=2,
            max_consecutive_losses=3,
        ),
        final_balance=1000.0 + net_profit,
    )


def test_build_v50_growth_refinement_variants_includes_required_names():
    variants = sweep.build_v50_growth_refinement_variants()
    names = [variant.variant_name for variant in variants]

    assert names == list(sweep.VARIANT_NAMES)
    assert len(names) == len(set(names))


def test_v50_edge_filter_blocks_long_outside_long_allowed_sessions(monkeypatch):
    def fake_signal(_df, config):
        return TradingSignal(
            timestamp=pd.Timestamp("2025-01-01 01:00:00").to_pydatetime(),
            symbol=config.symbol,
            timeframe=config.timeframe,
            side="BUY",
            entry_price=2350.0,
            stop_loss=2349.0,
            take_profit=2352.0,
            risk_reward=2.0,
            confidence=80.0,
            reason="V50 Pine technical approximation | Side=BUY | session=ASIA",
        )

    monkeypatch.setattr(v50_edge_filters.strategy_v50_pine, "generate_signal", fake_signal)
    signal_generator = v50_edge_filters.make_v50_edge_filter_signal_generator(
        v50_edge_filters.V50EdgeFilterVariant(
            "long_london_only",
            long_allowed_sessions=("LONDON",),
        )
    )
    signal = signal_generator(make_sweep_data(), StrategyConfig())

    assert signal.side == "NO_TRADE"
    assert "long session=ASIA not allowed" in signal.reason


def test_growth_refinement_sweep_generates_csv_with_required_columns(monkeypatch, tmp_path):
    def fake_run_variant(_df, variant, _strategy_config, _backtest_config):
        trade_count = sweep.VARIANT_NAMES.index(variant.variant_name) + 1
        return make_result(trade_count, float(trade_count), variant.variant_name)

    output_path = tmp_path / "v50_growth_refinement_sweep.csv"
    monkeypatch.setattr(sweep, "run_v50_growth_refinement_variant", fake_run_variant)

    report = sweep.run_v50_growth_refinement_sweep(
        df=make_sweep_data(),
        strategy_config=StrategyConfig(),
        backtest_config=BacktestConfig(warmup_candles=0),
        output_path=output_path,
    )
    exported = pd.read_csv(output_path)

    assert output_path.exists()
    assert set(exported["variant_name"]) == set(sweep.VARIANT_NAMES)
    assert set(report["strategy_name"]) == {sweep.BASE_STRATEGY_NAME}
    assert {
        "profit_drawdown_ratio",
        "max_consecutive_losses",
        "side_performance",
        "session_performance",
    }.issubset(exported.columns)


def test_growth_refinement_walk_forward_generates_summary_csv(monkeypatch, tmp_path):
    def fake_run_variant(df, variant, _strategy_config, _backtest_config):
        trade_count = 2 if len(df) else 0
        net_profit = 5.0 if variant.variant_name == "v50_growth_current" else -1.0
        return make_result(trade_count, net_profit, variant.variant_name)

    variants = sweep.build_v50_growth_refinement_variants()[:2]
    output_path = tmp_path / "v50_growth_refinement_walk_forward_quarter.csv"
    monkeypatch.setattr(sweep, "run_v50_growth_refinement_variant", fake_run_variant)

    report = sweep.run_v50_growth_refinement_walk_forward(
        df=make_sweep_data(rows=220),
        period="quarter",
        strategy_config=StrategyConfig(),
        backtest_config=BacktestConfig(warmup_candles=0),
        variants=variants,
        output_path=output_path,
    )
    exported = pd.read_csv(output_path)

    assert output_path.exists()
    assert set(exported["variant_name"]) == {variant.variant_name for variant in variants}
    assert {"total_periods", "active_periods", "stability_score"}.issubset(report.columns)


def test_growth_refinement_script_runs_and_exports_csv(tmp_path, monkeypatch, capsys):
    output_path = tmp_path / "v50_growth_refinement_sweep.csv"
    raw_path = tmp_path / "xauusd.csv"
    raw_path.write_text("placeholder", encoding="utf-8")

    def fake_run_sweep(*, output_path, **_kwargs):
        report = pd.DataFrame(
            [
                {
                    "strategy_name": sweep.BASE_STRATEGY_NAME,
                    "variant_name": "v50_growth_current",
                    "total_trades": 10,
                    "wins": 6,
                    "losses": 4,
                    "win_rate": 60.0,
                    "profit_factor": 1.2,
                    "net_profit": 10.0,
                    "max_drawdown": 5.0,
                    "expectancy": 1.0,
                    "profit_drawdown_ratio": 2.0,
                    "max_consecutive_losses": 2,
                    "long_trades": 5,
                    "long_net_profit": 7.0,
                    "long_profit_factor": 1.3,
                    "short_trades": 5,
                    "short_net_profit": 3.0,
                    "short_profit_factor": 1.1,
                    "side_performance": "{}",
                    "session_performance": "{}",
                }
            ],
            columns=sweep.SWEEP_COLUMNS,
        )
        report.to_csv(output_path, index=False)
        return report

    fake_settings = SimpleNamespace(
        trading=SimpleNamespace(symbol="XAUUSD", base_timeframe="15m", live_mode=False)
    )
    monkeypatch.setattr(run_v50_growth_refinement_sweep, "RAW_DATA_PATH", raw_path)
    monkeypatch.setattr(run_v50_growth_refinement_sweep, "DEFAULT_GROWTH_REFINEMENT_SWEEP_PATH", output_path)
    monkeypatch.setattr(run_v50_growth_refinement_sweep, "load_settings", lambda: fake_settings)
    monkeypatch.setattr(run_v50_growth_refinement_sweep, "load_csv_data", lambda _path: make_sweep_data())
    monkeypatch.setattr(run_v50_growth_refinement_sweep, "build_strategy_config", lambda _settings: StrategyConfig())
    monkeypatch.setattr(
        run_v50_growth_refinement_sweep,
        "build_backtest_config",
        lambda _settings: BacktestConfig(warmup_candles=0),
    )
    monkeypatch.setattr(run_v50_growth_refinement_sweep, "run_v50_growth_refinement_sweep", fake_run_sweep)
    monkeypatch.setattr("sys.argv", ["run_v50_growth_refinement_sweep.py"])

    run_v50_growth_refinement_sweep.main()
    output = capsys.readouterr().out

    assert output_path.exists()
    assert "V50 Growth Refinement Sweep" in output
    assert "No variant was promoted automatically." in output


def test_growth_refinement_analysis_ranking_and_category_picks():
    sweep_report = pd.DataFrame(
        {
            "variant_name": ["low", "balanced", "growth"],
            "profit_drawdown_ratio": [4.0, 5.0, 3.0],
            "profit_factor": [1.2, 1.3, 1.1],
            "net_profit": [100.0, 160.0, 250.0],
            "max_drawdown": [20.0, 32.0, 80.0],
            "total_trades": [80, 120, 200],
        }
    )
    month_report = pd.DataFrame(
        {
            "variant_name": ["low", "balanced", "growth"],
            "stability_score": [1.0, 1.5, 1.1],
        }
    )

    ranking = analyze_v50_growth_refinement.build_growth_refinement_ranking(
        sweep_report,
        month=month_report,
    )

    assert ranking.iloc[0]["variant_name"] == "balanced"
    assert analyze_v50_growth_refinement.select_best_low_risk(ranking)["variant_name"] == "low"
    assert analyze_v50_growth_refinement.select_best_balanced(ranking)["variant_name"] == "balanced"
    assert analyze_v50_growth_refinement.select_best_growth(ranking)["variant_name"] == "growth"


def test_growth_refinement_research_only_and_live_mode_default_false():
    config = load_yaml_config()
    checked_files = [
        Path("scripts/run_v50_growth_refinement_sweep.py"),
        Path("scripts/analyze_v50_growth_refinement.py"),
        Path("src/strategy_lab/v50_growth_refinement_sweep.py"),
    ]

    assert config["trading"]["live_mode"] is False
    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
