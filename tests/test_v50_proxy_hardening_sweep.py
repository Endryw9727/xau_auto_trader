from pathlib import Path

import pandas as pd

from scripts import run_v50_proxy_hardening_sweep as sweep_script
from src.backtesting.backtester import BacktestConfig, BacktestResult
from src.backtesting.metrics import calculate_metrics
from src.strategy.rules import StrategyConfig
from src.strategy_lab.v50_proxy_hardening import (
    PROXY_HARDENING_VARIANT_NAMES,
    SWEEP_COLUMNS,
    annotate_hardening_interest,
    build_proxy_hardening_variants,
    run_proxy_hardening_sweep,
    validate_proxy_hardening_variant,
)


def make_market_data(days: int = 8) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "Open": [100.0] * days,
            "High": [105.0] * days,
            "Low": [99.0] * days,
            "Close": [103.0] * days,
            "Volume": [1.0] * days,
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


def test_proxy_hardening_variants_are_stable_and_leakage_safe():
    variants = build_proxy_hardening_variants()
    names = [variant.variant_name for variant in variants]

    assert names == list(PROXY_HARDENING_VARIANT_NAMES)
    assert len(names) == len(set(names))
    for variant in variants:
        validate_proxy_hardening_variant(variant)
        assert "bars" not in repr(variant).lower()


def test_proxy_hardening_sweep_generates_csv(monkeypatch, tmp_path):
    def fake_run_variant(_df, variant, _strategy_config, _backtest_config):
        return make_result(variant.variant_name)

    output_path = tmp_path / "hardening_sweep.csv"
    monkeypatch.setattr(
        "src.strategy_lab.v50_proxy_hardening.run_proxy_hardening_variant",
        fake_run_variant,
    )
    report, results = run_proxy_hardening_sweep(
        df=make_market_data(),
        strategy_config=StrategyConfig(),
        backtest_config=BacktestConfig(warmup_candles=1),
        output_path=output_path,
    )

    assert output_path.exists()
    assert set(report["variant_name"]) == set(PROXY_HARDENING_VARIANT_NAMES)
    assert set(SWEEP_COLUMNS).issubset(report.columns)
    assert set(results) == set(PROXY_HARDENING_VARIANT_NAMES)


def test_annotate_hardening_interest_applies_constraints():
    sweep = pd.DataFrame(
        [
            {
                "variant_name": "proxy_hardened_balanced",
                "total_trades": 900,
                "average_trades_per_day": 0.80,
                "profit_factor": 1.25,
                "max_drawdown": 130.0,
                "max_consecutive_losses": 9,
                "leakage_safe": True,
            }
        ]
    )
    stress = pd.DataFrame(
        [{"variant_name": "proxy_hardened_balanced", "scenario": "spread_slippage_medium", "profit_factor": 1.21}]
    )
    monte_carlo = pd.DataFrame(
        [{"strategy_name": "proxy_hardened_balanced", "probability_drawdown_over_20_percent": 20.0}]
    )

    annotated = annotate_hardening_interest(sweep, stress, monte_carlo, base_probability_dd20=32.4)

    assert bool(annotated.iloc[0]["anti_overfit_pass"]) is True


def test_proxy_hardening_sweep_script_runs(monkeypatch, tmp_path, capsys):
    sweep_path = tmp_path / "sweep.csv"
    stress_path = tmp_path / "stress.csv"
    mc_path = tmp_path / "mc.csv"
    raw_path = tmp_path / "xauusd.csv"
    raw_path.write_text("placeholder", encoding="utf-8")
    sweep_report = pd.DataFrame(
        [
            {
                "strategy_name": "v50_proxy_balanced_candidate",
                "variant_name": "proxy_hardened_base",
                "total_trades": 900,
                "average_trades_per_day": 0.8,
                "win_rate": 40.0,
                "profit_factor": 1.24,
                "net_profit": 100.0,
                "max_drawdown": 100.0,
                "expectancy": 0.1,
                "profit_drawdown_ratio": 1.0,
                "max_consecutive_losses": 9,
                "positive_months": 10,
                "negative_months": 2,
                "anti_overfit_pass": False,
                "leakage_safe": True,
            }
        ]
    )
    stress_report = pd.DataFrame(
        [{"variant_name": "proxy_hardened_base", "scenario": "spread_slippage_medium", "profit_factor": 1.21}]
    )
    mc_report = pd.DataFrame(
        [
            {
                "strategy_name": "proxy_hardened_base",
                "probability_drawdown_over_20_percent": 20.0,
                "median_final_profit": 100.0,
                "median_max_drawdown": 80.0,
                "worst_5pct_drawdown": 120.0,
                "probability_of_loss": 0.0,
            }
        ]
    )

    monkeypatch.setattr(sweep_script, "RAW_DATA_PATH", raw_path)
    monkeypatch.setattr(sweep_script, "DEFAULT_PROXY_HARDENING_SWEEP_PATH", sweep_path)
    monkeypatch.setattr(sweep_script, "DEFAULT_PROXY_HARDENING_STRESS_PATH", stress_path)
    monkeypatch.setattr(sweep_script, "DEFAULT_PROXY_HARDENING_MONTE_CARLO_PATH", mc_path)
    monkeypatch.setattr(sweep_script, "load_csv_data", lambda _path: make_market_data())
    monkeypatch.setattr(sweep_script, "run_proxy_hardening_sweep", lambda **_kwargs: (sweep_report.copy(), {}))
    monkeypatch.setattr(sweep_script, "run_proxy_hardening_stress", lambda **_kwargs: stress_report.copy())
    monkeypatch.setattr(sweep_script, "run_proxy_hardening_monte_carlo", lambda **_kwargs: mc_report.copy())

    sweep_script.main()
    output = capsys.readouterr().out

    assert sweep_path.exists()
    assert "V50 Proxy Hardening Sweep" in output
    assert "No candidate was promoted automatically." in output


def test_proxy_hardening_sources_are_research_only():
    for path in [
        Path("src/strategy_lab/v50_proxy_hardening.py"),
        Path("scripts/run_v50_proxy_hardening_sweep.py"),
    ]:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
