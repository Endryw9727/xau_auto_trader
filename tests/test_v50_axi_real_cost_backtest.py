from pathlib import Path

import pandas as pd

from scripts import run_v50_axi_real_cost_backtest as script
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
            "strategy_name": [strategy_name] * 4,
            "entry_time": pd.date_range("2025-01-01 09:00:00", periods=4, freq="12h"),
            "side": ["BUY", "SELL", "BUY", "SELL"],
            "session": ["LONDON", "LONDON", "NEW YORK", "LONDON"],
            "entry_price": [100.0, 101.0, 102.0, 103.0],
            "stop_loss": [98.0, 103.0, 100.0, 105.0],
            "take_profit": [104.0, 97.0, 106.0, 99.0],
            "position_size": [1.0] * 4,
            "score_long": [82.0, 55.0, 78.0, 60.0],
            "score_short": [50.0, 84.0, 56.0, 80.0],
            "profit_loss": [12.0, -4.0, 10.0, -3.0],
            "pnl": [12.0, -4.0, 10.0, -3.0],
        }
    )
    metrics = calculate_metrics(trades, initial_balance=1000.0)
    return BacktestResult(trades=trades, metrics=metrics, final_balance=1015.0)


def test_axi_real_cost_backtest_generates_rows_and_csv(tmp_path):
    source_results = {
        "v50_final_balanced_strategy": make_result("v50_final_balanced_strategy"),
        "v50_proxy_balanced_candidate": make_result("v50_proxy_balanced_candidate"),
        "proxy_hardened_no_worst_hours": make_result("proxy_hardened_no_worst_hours"),
        "proxy_hardened_score_plus": make_result("proxy_hardened_score_plus"),
    }
    profiles = [
        cost_aware.CostProfile(
            "axi_pro_realistic",
            0.0,
            0.0,
            0.0,
            spread_pips=0.0,
            slippage_pips=0.0,
            commission_per_001_lot_per_side=0.04,
            profile_group="axi",
        )
    ]
    output_path = tmp_path / "axi.csv"

    report = cost_aware.run_axi_real_cost_backtest(
        source_results=source_results,
        market_data=make_market_data(),
        profiles=profiles,
        output_path=output_path,
    )

    assert output_path.exists()
    assert set(cost_aware.AXI_REAL_COST_COLUMNS).issubset(report.columns)
    assert "proxy_hardened_no_worst_hours_high_margin" in set(report["strategy_name"])
    assert (report["total_commission"] >= 0).all()
    assert (report["average_cost_per_trade"] >= 0).all()


def test_axi_real_cost_backtest_script_runs(monkeypatch, tmp_path, capsys):
    raw_path = tmp_path / "xauusd.csv"
    output_path = tmp_path / "axi.csv"
    raw_path.write_text("placeholder", encoding="utf-8")
    fake_report = pd.DataFrame(
        [
            {
                "strategy_name": "v50_proxy_balanced_candidate",
                "cost_profile": "axi_pro_realistic",
                "total_trades": 900,
                "average_trades_per_day": 0.8,
                "win_rate": 40.0,
                "gross_profit_factor": 1.3,
                "net_profit_factor": 1.29,
                "gross_net_profit": 100.0,
                "net_profit_after_costs": 95.0,
                "total_commission": 5.0,
                "total_spread_cost": 0.0,
                "total_slippage_cost": 0.0,
                "total_cost": 5.0,
                "average_cost_per_trade": 0.08,
                "average_trade_after_costs": 0.1,
                "max_drawdown_after_costs": 100.0,
                "expectancy_after_costs": 0.1,
                "profit_drawdown_ratio_after_costs": 0.95,
                "max_consecutive_losses": 8,
                "positive_months": 10,
                "negative_months": 2,
                "average_lot": 0.01,
                "max_lot": 0.01,
                "commission_round_turn_per_001_lot": 0.08,
                "profile_note": "test",
            }
        ]
    )

    monkeypatch.setattr(script, "RAW_DATA_PATH", raw_path)
    monkeypatch.setattr(script, "DEFAULT_AXI_REAL_COST_BACKTEST_PATH", output_path)
    monkeypatch.setattr(script, "load_csv_data", lambda _path: make_market_data())
    monkeypatch.setattr(script, "run_axi_source_backtests", lambda **_kwargs: {})

    def fake_run_backtest(**_kwargs):
        fake_report.to_csv(output_path, index=False)
        return fake_report

    monkeypatch.setattr(script, "run_axi_real_cost_backtest", fake_run_backtest)

    script.main()
    output = capsys.readouterr().out

    assert output_path.exists()
    assert "V50 Axi Real-Cost Backtest" in output
    assert "No candidate was promoted automatically." in output


def test_axi_real_cost_backtest_sources_are_research_only():
    for path in [
        Path("src/strategy_lab/v50_cost_aware.py"),
        Path("scripts/run_v50_axi_real_cost_backtest.py"),
    ]:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
