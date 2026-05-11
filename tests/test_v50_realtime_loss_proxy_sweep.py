from pathlib import Path

import pandas as pd

from scripts import analyze_v50_realtime_proxy_selection as selection_script
from scripts import run_v50_realtime_loss_proxy_sweep as sweep_script
from src.backtesting.backtester import BacktestConfig, BacktestResult
from src.backtesting.metrics import calculate_metrics
from src.strategy.rules import StrategyConfig
from src.strategy_lab.strategy_v50_candidates import FINAL_BALANCED_STRATEGY_NAME
from src.strategy_lab.v50_realtime_loss_proxy_sweep import (
    REALTIME_PROXY_VARIANT_NAMES,
    REALTIME_SWEEP_COLUMNS,
    build_realtime_loss_proxy_variants,
    make_realtime_loss_proxy_signal_generator,
    run_realtime_loss_proxy_sweep,
    top_realtime_proxy_variant_names,
    validate_variant_no_leakage,
)


def make_feature_window(score_long: float = 72.0, session: str = "LONDON") -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp("2025-01-01 11:00:00")])
    return pd.DataFrame(
        {
            "Open": [100.0],
            "High": [101.0],
            "Low": [99.0],
            "Close": [100.0],
            "Volume": [1.0],
            "ATR_14": [1.0],
            "v50_score_long": [score_long],
            "v50_score_short": [20.0],
            "v50_quality_long_ok": [True],
            "v50_quality_short_ok": [False],
            "v50_setup_long": [True],
            "v50_setup_short": [False],
            "v50_session": [session],
        },
        index=index,
    )


def make_market_data(days: int = 8) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "Open": [100.0] * len(dates),
            "High": [105.0] * len(dates),
            "Low": [99.0] * len(dates),
            "Close": [103.0] * len(dates),
            "Volume": [1.0] * len(dates),
        },
        index=dates,
    )


def make_result(variant_name: str, trade_count: int = 8) -> BacktestResult:
    pnl = [10.0, -4.0, 9.0, -3.0, 8.0, -2.0, 7.0, -1.0][:trade_count]
    trades = pd.DataFrame(
        {
            "strategy_name": [variant_name] * len(pnl),
            "entry_time": pd.date_range("2025-01-01 09:00:00", periods=len(pnl), freq="D"),
            "side": ["BUY", "SELL"] * (len(pnl) // 2),
            "side_label": ["LONG", "SHORT"] * (len(pnl) // 2),
            "session": ["LONDON", "NEW YORK"] * (len(pnl) // 2),
            "pnl": pnl,
            "profit_loss": pnl,
        }
    )
    metrics = calculate_metrics(trades, initial_balance=1000.0)
    return BacktestResult(trades=trades, metrics=metrics, final_balance=1000.0 + sum(pnl))


def test_realtime_loss_proxy_variants_are_stable_and_unique():
    variants = build_realtime_loss_proxy_variants()
    names = [variant.variant_name for variant in variants]

    assert names == list(REALTIME_PROXY_VARIANT_NAMES)
    assert len(names) == len(set(names))
    for variant in variants:
        validate_variant_no_leakage(variant)


def test_realtime_proxy_signal_generator_blocks_low_score_bucket():
    variant = next(v for v in build_realtime_loss_proxy_variants() if v.variant_name == "proxy_block_score_70_74")
    signal = make_realtime_loss_proxy_signal_generator(variant)(make_feature_window(score_long=72.0), StrategyConfig())

    assert signal.side == "NO_TRADE"
    assert "proxy_block_score_70_74" in signal.reason


def test_realtime_proxy_signal_generator_can_emit_valid_buy_signal():
    variant = next(v for v in build_realtime_loss_proxy_variants() if v.variant_name == "proxy_base")
    signal = make_realtime_loss_proxy_signal_generator(variant)(make_feature_window(score_long=82.0), StrategyConfig())

    assert signal.side == "BUY"
    assert signal.stop_loss is not None
    assert signal.take_profit is not None


def test_realtime_loss_proxy_sweep_generates_csv(monkeypatch, tmp_path):
    def fake_run_variant(_df, variant, _strategy_config, _backtest_config):
        return make_result(variant.variant_name)

    output_path = tmp_path / "realtime_loss_proxy_sweep.csv"
    monkeypatch.setattr(
        "src.strategy_lab.v50_realtime_loss_proxy_sweep.run_realtime_loss_proxy_variant",
        fake_run_variant,
    )
    report = run_realtime_loss_proxy_sweep(
        df=make_market_data(),
        strategy_config=StrategyConfig(),
        backtest_config=BacktestConfig(warmup_candles=1),
        output_path=output_path,
    )

    assert output_path.exists()
    assert set(report["variant_name"]) == set(REALTIME_PROXY_VARIANT_NAMES)
    assert set(REALTIME_SWEEP_COLUMNS).issubset(report.columns)
    assert report["leakage_safe"].all()


def test_realtime_loss_proxy_sweep_script_runs(monkeypatch, tmp_path, capsys):
    sweep_path = tmp_path / "sweep.csv"
    stress_path = tmp_path / "stress.csv"
    raw_path = tmp_path / "xauusd.csv"
    raw_path.write_text("placeholder", encoding="utf-8")

    sweep_report = pd.DataFrame(
        [
            {
                "strategy_name": FINAL_BALANCED_STRATEGY_NAME,
                "variant_name": "proxy_base",
                "total_trades": 800,
                "average_trades_per_day": 0.8,
                "active_day_ratio": 0.7,
                "win_rate": 40.0,
                "profit_factor": 1.2,
                "net_profit": 100.0,
                "max_drawdown": 80.0,
                "expectancy": 0.1,
                "profit_drawdown_ratio": 1.25,
                "max_consecutive_losses": 9,
                "positive_months": 8,
                "negative_months": 4,
                "removed_trade_pct": 0.0,
                "leakage_safe": True,
                "anti_overfit_pass": False,
            }
        ]
    )
    stress_report = pd.DataFrame(
        [
            {
                "strategy_name": FINAL_BALANCED_STRATEGY_NAME,
                "variant_name": "proxy_base",
                "scenario": "base",
                "total_trades": 800,
                "win_rate": 40.0,
                "profit_factor": 1.2,
                "net_profit": 100.0,
                "max_drawdown": 80.0,
                "expectancy": 0.1,
                "profit_drawdown_ratio": 1.25,
                "max_consecutive_losses": 9,
            }
        ]
    )

    def fake_sweep(**_kwargs):
        sweep_report.to_csv(sweep_path, index=False)
        return sweep_report

    def fake_stress(**_kwargs):
        stress_report.to_csv(stress_path, index=False)
        return stress_report

    monkeypatch.setattr(sweep_script, "RAW_DATA_PATH", raw_path)
    monkeypatch.setattr(sweep_script, "DEFAULT_REALTIME_LOSS_PROXY_SWEEP_PATH", sweep_path)
    monkeypatch.setattr(sweep_script, "DEFAULT_REALTIME_LOSS_PROXY_STRESS_PATH", stress_path)
    monkeypatch.setattr(sweep_script, "load_csv_data", lambda _path: make_market_data())
    monkeypatch.setattr(sweep_script, "run_realtime_loss_proxy_sweep", fake_sweep)
    monkeypatch.setattr(sweep_script, "run_realtime_loss_proxy_stress", fake_stress)

    sweep_script.main()
    output = capsys.readouterr().out

    assert sweep_path.exists()
    assert stress_path.exists()
    assert "V50 Realtime Loss Proxy Sweep" in output
    assert "No variant was promoted automatically." in output


def test_realtime_proxy_selection_helpers(tmp_path):
    report = pd.DataFrame(
        [
            {
                "variant_name": "proxy_base",
                "total_trades": 800,
                "average_trades_per_day": 0.8,
                "active_day_ratio": 0.7,
                "profit_factor": 1.20,
                "net_profit": 100.0,
                "max_drawdown": 100.0,
                "profit_drawdown_ratio": 1.0,
                "max_consecutive_losses": 11,
                "anti_overfit_pass": False,
                "leakage_safe": True,
            },
            {
                "variant_name": "proxy_quality_combo",
                "total_trades": 760,
                "average_trades_per_day": 0.76,
                "active_day_ratio": 0.66,
                "profit_factor": 1.28,
                "net_profit": 120.0,
                "max_drawdown": 82.0,
                "profit_drawdown_ratio": 1.46,
                "max_consecutive_losses": 8,
                "anti_overfit_pass": True,
                "leakage_safe": True,
            },
        ]
    )
    ranking = selection_script.prepare_realtime_proxy_ranking(report)
    base = selection_script.base_row(ranking)

    assert selection_script.select_best_profit_factor(ranking)["variant_name"] == "proxy_quality_combo"
    assert selection_script.exists_pf_with_frequency(ranking, 1.25, 0.75)
    assert selection_script.exists_dd_below_with_base_pf(ranking, base, 90.0)
    assert top_realtime_proxy_variant_names(ranking, limit=2)[0] == "proxy_quality_combo"


def test_realtime_loss_proxy_sources_are_research_only():
    checked_files = [
        Path("src/strategy_lab/v50_realtime_loss_proxy_sweep.py"),
        Path("scripts/run_v50_realtime_loss_proxy_sweep.py"),
        Path("scripts/analyze_v50_realtime_proxy_selection.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
