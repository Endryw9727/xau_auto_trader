import pandas as pd

from scripts import run_paper_simulation as script
from src.paper.paper_engine import PaperTradingConfig


def make_config() -> PaperTradingConfig:
    return PaperTradingConfig(
        strategy_name="proxy_hardened_no_worst_hours",
        backup_strategy="proxy_hardened_no_worst_hours_high_margin",
        symbol="XAUUSD",
        base_timeframe="15m",
        live_mode=False,
        paper_mode=True,
        initial_equity=1000.0,
        min_lot=0.01,
        lot_step=0.01,
        equity_step=1000.0,
        max_lot=0.10,
        commission_per_001_lot_per_side=0.04,
        spread_pips=0.0,
        slippage_pips=0.0,
        conservative_slippage_pips=0.1,
        max_trades_per_day=2,
        max_daily_loss_pct=3.0,
        max_consecutive_losses_day=2,
        max_consecutive_losses_total_warning=8,
        max_drawdown_warning_pct=8.0,
        max_drawdown_stop_pct=12.0,
        min_score_required=72.0,
        no_trade_after_daily_stop=True,
    )


def test_run_paper_simulation_script_runs(monkeypatch, tmp_path, capsys):
    raw_path = tmp_path / "xauusd.csv"
    raw_path.write_text("placeholder", encoding="utf-8")
    fake_summary = pd.DataFrame(
        [
            {
                "strategy_name": "proxy_hardened_no_worst_hours",
                "starting_equity": 1000.0,
                "ending_equity": 1200.0,
                "net_profit": 200.0,
                "profit_factor_net": 1.3,
                "max_dd_pct": 8.0,
                "max_dd_eur": 80.0,
                "total_trades": 800,
                "trades_per_day": 0.7,
                "win_rate": 40.0,
                "avg_win": 2.0,
                "avg_loss": -1.0,
                "expectancy": 0.25,
                "max_consecutive_losses": 8,
                "worst_day": -20.0,
                "worst_week": -30.0,
                "worst_month": -50.0,
                "months_positive": 10,
                "months_negative": 3,
                "no_trade_days": 100,
                "max_no_trade_days": 5,
                "time_to_1500_if_reached": pd.NA,
                "time_to_2000_if_reached": pd.NA,
                "returned_below_1000_after_growth": False,
                "drawdown_over_8_pct": True,
                "drawdown_over_10_pct": False,
                "drawdown_over_12_pct": False,
            }
        ]
    )

    monkeypatch.setattr(script, "RAW_DATA_PATH", raw_path)
    monkeypatch.setattr(script, "load_paper_trading_config", lambda _path: make_config())
    monkeypatch.setattr(script, "load_csv_data", lambda _path: pd.DataFrame({"Close": [1.0]}, index=pd.to_datetime(["2025-01-01"])))
    monkeypatch.setattr(script, "run_axi_source_backtests", lambda **_kwargs: {})
    monkeypatch.setattr(script, "run_controlled_paper_simulation", lambda **_kwargs: (fake_summary, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()))

    script.main()
    output = capsys.readouterr().out

    assert "Controlled Paper Simulation" in output
    assert "proxy_hardened_no_worst_hours" in output
    assert "No strategy was promoted automatically." in output


def test_paper_simulation_script_is_research_only():
    source = open("scripts/run_paper_simulation.py", encoding="utf-8").read()
    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
