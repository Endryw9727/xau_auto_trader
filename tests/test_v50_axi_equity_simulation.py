from pathlib import Path

import pandas as pd

from scripts import run_v50_axi_equity_simulation as script
from src.backtesting.backtester import BacktestResult
from src.backtesting.metrics import calculate_metrics
from src.strategy_lab import v50_axi_equity as equity
from src.strategy_lab.v50_cost_aware import AxiSizingConfig, build_cost_profiles


def make_trades(strategy_name: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strategy_name": [strategy_name] * 3,
            "entry_time": pd.to_datetime(["2025-01-01 09:00:00", "2025-01-02 09:00:00", "2025-01-03 09:00:00"]),
            "exit_time": pd.to_datetime(["2025-01-01 10:00:00", "2025-01-02 10:00:00", "2025-01-03 10:00:00"]),
            "side": ["BUY", "SELL", "BUY"],
            "session": ["LONDON", "LONDON", "NEW YORK"],
            "entry_price": [100.0, 100.0, 100.0],
            "exit_price": [110.0, 95.0, 90.0],
            "stop_loss": [95.0, 105.0, 95.0],
            "take_profit": [110.0, 95.0, 110.0],
            "position_size": [1.0, 1.0, 1.0],
            "score_long": [80.0, 50.0, 82.0],
            "score_short": [50.0, 84.0, 55.0],
            "profit_loss": [10.0, 5.0, -10.0],
            "pnl": [10.0, 5.0, -10.0],
        }
    )


def make_result(strategy_name: str) -> BacktestResult:
    trades = make_trades(strategy_name)
    return BacktestResult(
        trades=trades,
        metrics=calculate_metrics(trades, initial_balance=1000.0),
        final_balance=1005.0,
    )


def test_simulate_axi_equity_curve_uses_lot_ladder_and_costs():
    profiles = {profile.name: profile for profile in build_cost_profiles()}
    scenario = equity.AxiEquityScenario("axi_realistic_slippage_0_0", profiles["axi_pro_realistic"])
    curve = equity.simulate_axi_equity_curve(
        make_trades("v50_proxy_balanced_candidate"),
        strategy_name="v50_proxy_balanced_candidate",
        scenario=scenario,
        sizing_config=AxiSizingConfig(),
    )

    assert set(equity.EQUITY_CURVE_COLUMNS).issubset(curve.columns)
    assert curve.iloc[0]["lot_size"] == 0.01
    assert curve.iloc[0]["commission_eur"] == 0.08
    assert curve.iloc[-1]["equity_after"] > 1000.0
    assert curve["drawdown_eur"].max() >= 0.0


def test_axi_equity_simulation_exports_all_reports(tmp_path):
    source_results = {
        "v50_proxy_balanced_candidate": make_result("v50_proxy_balanced_candidate"),
        "proxy_hardened_score_plus": make_result("proxy_hardened_score_plus"),
        "proxy_hardened_no_worst_hours": make_result("proxy_hardened_no_worst_hours"),
    }
    summary_path = tmp_path / "summary.csv"
    curve_path = tmp_path / "curve.csv"
    monthly_path = tmp_path / "monthly.csv"

    summary, curve, monthly = equity.run_axi_equity_simulation(
        source_results,
        output_summary_path=summary_path,
        output_curve_path=curve_path,
        output_monthly_path=monthly_path,
    )

    assert summary_path.exists()
    assert curve_path.exists()
    assert monthly_path.exists()
    assert set(equity.SUMMARY_COLUMNS).issubset(summary.columns)
    assert set(equity.EQUITY_CURVE_COLUMNS).issubset(curve.columns)
    assert set(equity.MONTHLY_COLUMNS).issubset(monthly.columns)
    assert "proxy_hardened_no_worst_hours_high_margin" in set(summary["strategy_name"])


def test_axi_equity_simulation_script_runs(monkeypatch, tmp_path, capsys):
    raw_path = tmp_path / "xauusd.csv"
    raw_path.write_text("placeholder", encoding="utf-8")
    summary_path = tmp_path / "summary.csv"
    curve_path = tmp_path / "curve.csv"
    monthly_path = tmp_path / "monthly.csv"
    fake_summary = pd.DataFrame(
        [
            {
                "strategy_name": "v50_proxy_balanced_candidate",
                "scenario": "axi_realistic_slippage_0_0",
                "ending_equity": 1100.0,
                "net_profit_eur": 100.0,
                "max_drawdown_percent": 5.0,
                "total_trades": 10,
                "trades_per_day": 1.0,
                "profit_factor_net": 1.3,
                "max_consecutive_losses": 2,
                "lot_max": 0.01,
            }
        ]
    )

    monkeypatch.setattr(script, "RAW_DATA_PATH", raw_path)
    monkeypatch.setattr(script, "DEFAULT_AXI_EQUITY_SIMULATION_PATH", summary_path)
    monkeypatch.setattr(script, "DEFAULT_AXI_EQUITY_CURVE_PATH", curve_path)
    monkeypatch.setattr(script, "DEFAULT_AXI_MONTHLY_EQUITY_PATH", monthly_path)
    monkeypatch.setattr(script, "load_csv_data", lambda _path: pd.DataFrame({"Close": [1.0]}))
    monkeypatch.setattr(script, "run_axi_source_backtests", lambda **_kwargs: {})

    def fake_run(**_kwargs):
        fake_summary.to_csv(summary_path, index=False)
        pd.DataFrame({"x": [1]}).to_csv(curve_path, index=False)
        pd.DataFrame({"x": [1]}).to_csv(monthly_path, index=False)
        return fake_summary, pd.DataFrame({"x": [1]}), pd.DataFrame({"x": [1]})

    monkeypatch.setattr(script, "run_axi_equity_simulation", fake_run)

    script.main()
    output = capsys.readouterr().out

    assert summary_path.exists()
    assert "V50 Axi Equity Simulation" in output
    assert "No candidate was promoted automatically." in output


def test_axi_equity_sources_are_research_only():
    for path in [
        Path("src/strategy_lab/v50_axi_equity.py"),
        Path("scripts/run_v50_axi_equity_simulation.py"),
    ]:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
