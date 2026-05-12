from pathlib import Path
import inspect

import pandas as pd

from scripts import run_v50_cost_aware_sweep as sweep_script
from src.backtesting.backtester import BacktestResult
from src.backtesting.metrics import calculate_metrics
from src.strategy_lab import v50_cost_aware as cost_aware


def make_market_data(days: int = 4) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "Open": [100.0] * days,
            "High": [105.0] * days,
            "Low": [98.0] * days,
            "Close": [102.0] * days,
            "Volume": [1.0] * days,
        },
        index=index,
    )


def make_result(strategy_name: str) -> BacktestResult:
    trades = pd.DataFrame(
        {
            "strategy_name": [strategy_name] * 6,
            "entry_time": pd.date_range("2025-01-01 09:00:00", periods=6, freq="12h"),
            "side": ["BUY", "SELL", "BUY", "SELL", "BUY", "SELL"],
            "session": ["LONDON", "LONDON", "NEW YORK", "LONDON", "ASIA", "LONDON"],
            "entry_price": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            "stop_loss": [98.0, 103.0, 100.0, 105.0, 102.0, 107.0],
            "take_profit": [104.0, 97.0, 106.0, 99.0, 108.0, 101.0],
            "position_size": [1.0] * 6,
            "score_long": [82.0, 55.0, 78.0, 60.0, 76.0, 58.0],
            "score_short": [50.0, 84.0, 56.0, 80.0, 52.0, 79.0],
            "profit_loss": [12.0, -4.0, 10.0, -3.0, 8.0, -2.0],
            "pnl": [12.0, -4.0, 10.0, -3.0, 8.0, -2.0],
        }
    )
    metrics = calculate_metrics(trades, initial_balance=1000.0)
    return BacktestResult(trades=trades, metrics=metrics, final_balance=1021.0)


def test_cost_aware_variants_are_stable_and_leakage_safe():
    variants = cost_aware.build_cost_aware_variants()
    names = [variant.variant_name for variant in variants]

    assert names == list(cost_aware.COST_AWARE_VARIANT_NAMES)
    assert len(names) == len(set(names))
    for variant in variants:
        cost_aware.validate_cost_aware_variant(variant)


def test_cost_aware_sweep_generates_csv(tmp_path):
    source_results = {
        "v50_proxy_balanced_candidate": make_result("v50_proxy_balanced_candidate"),
        "proxy_hardened_no_worst_hours": make_result("proxy_hardened_no_worst_hours"),
    }
    profiles = [cost_aware.CostProfile("cost_test", 0.1, 0.1, 0.2)]
    variants = [cost_aware.CostAwareVariant("costaware_base"), cost_aware.CostAwareVariant("costaware_min_score_plus", min_score=80.0)]

    output_path = tmp_path / "sweep.csv"
    report = cost_aware.run_cost_aware_sweep(
        source_results=source_results,
        market_data=make_market_data(),
        profiles=profiles,
        variants=variants,
        output_path=output_path,
    )

    assert output_path.exists()
    assert set(cost_aware.SWEEP_COLUMNS).issubset(report.columns)
    assert len(report) == 4
    assert (report["total_cost"] >= 0).all()
    assert (report["net_profit_factor"] >= 0).all()


def test_cost_aware_filter_uses_entry_known_columns_only():
    source = inspect.getsource(cost_aware.apply_cost_aware_filter).lower()

    for token in ["pnl", "exit_time", "bars_in_trade", "trade_result", "drawdown"]:
        assert token not in source


def test_cost_aware_sweep_script_runs(monkeypatch, tmp_path, capsys):
    raw_path = tmp_path / "xauusd.csv"
    raw_path.write_text("placeholder", encoding="utf-8")
    output_path = tmp_path / "cost_sweep.csv"
    fake_report = pd.DataFrame(
        [
            {
                "source_variant": "v50_proxy_balanced_candidate",
                "variant_name": "costaware_base",
                "cost_profile": "cost_medium",
                "total_trades": 900,
                "average_trades_per_day": 0.8,
                "win_rate": 40.0,
                "gross_profit_factor": 1.3,
                "net_profit_factor": 1.21,
                "gross_net_profit": 100.0,
                "net_profit": 80.0,
                "total_cost": 20.0,
                "average_cost_per_trade": 0.02,
                "max_drawdown": 100.0,
                "expectancy_net": 0.1,
                "profit_drawdown_ratio_net": 0.8,
                "max_consecutive_losses": 8,
                "positive_months": 6,
                "negative_months": 2,
                "pf_without_top_1pct": 1.15,
                "pf_without_top_3pct": 1.10,
                "pf_without_top_5pct": 1.05,
                "pf_without_top_10pct": 0.95,
                "net_profit_without_top_5pct": 50.0,
                "max_drawdown_without_top_5pct": 110.0,
                "anti_overfit_pass": True,
                "leakage_safe": True,
            }
        ]
    )

    monkeypatch.setattr(sweep_script, "RAW_DATA_PATH", raw_path)
    monkeypatch.setattr(sweep_script, "DEFAULT_COST_AWARE_SWEEP_PATH", output_path)
    monkeypatch.setattr(sweep_script, "load_csv_data", lambda _path: make_market_data())
    monkeypatch.setattr(sweep_script, "run_source_variant_backtests", lambda **_kwargs: {})

    def fake_run_sweep(**_kwargs):
        fake_report.to_csv(output_path, index=False)
        return fake_report

    monkeypatch.setattr(sweep_script, "run_cost_aware_sweep", fake_run_sweep)

    sweep_script.main()
    output = capsys.readouterr().out

    assert output_path.exists()
    assert "V50 Cost-Aware Sweep" in output
    assert "No candidate was promoted automatically." in output


def test_cost_aware_sources_are_research_only():
    for path in [
        Path("src/strategy_lab/v50_cost_aware.py"),
        Path("scripts/run_v50_cost_aware_sweep.py"),
    ]:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
