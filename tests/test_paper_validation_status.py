import pandas as pd

from scripts import check_paper_validation_status as script
from src.paper import paper_monitor as monitor


def make_monitor_summary(max_drawdown: float = 10.0, max_losses: int = 10) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "strategy_name": "proxy_hardened_no_worst_hours",
                "report_as_of": "2025-01-08",
                "status": "WARNING",
                "warning_reasons": "",
                "stop_reasons": "",
                "equity_current": 1200.0,
                "total_profit_loss": 200.0,
                "current_drawdown_eur": 0.0,
                "current_drawdown_pct": 0.0,
                "max_drawdown_eur": 100.0,
                "max_drawdown_pct": max_drawdown,
                "total_trades": 120,
                "trades_today": 1,
                "trades_week": 3,
                "trades_month": 20,
                "profit_factor_total": 1.3,
                "profit_factor_last_30": 1.2,
                "profit_factor_last_50": 1.1,
                "win_rate_total": 40.0,
                "win_rate_last_30": 42.0,
                "max_consecutive_losses": max_losses,
                "current_consecutive_losses": 0,
                "daily_loss_current": 0.0,
                "daily_loss_current_pct": 0.0,
                "weekly_loss_current": 0.0,
                "weekly_loss_current_pct": 0.0,
                "total_no_trade_days": 5,
                "current_no_trade_days": 0,
                "last_trade_time": "2025-01-08 09:00:00",
                "last_entry_reason": "test",
                "last_session": "LONDON",
                "last_result": "WIN",
            }
        ]
    )


def make_daily_summary() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strategy_name": ["proxy_hardened_no_worst_hours"] * 35,
            "date": pd.date_range("2025-01-01", periods=35, freq="D"),
            "trades": [1] * 35,
            "net_profit": [1.0] * 35,
        }
    )


def test_load_validation_rules_keeps_allow_live_false():
    rules = monitor.load_validation_rules("config/paper_validation_rules.yaml")

    assert rules.min_paper_trades_before_live == 60
    assert rules.ideal_paper_trades_before_live == 100
    assert rules.allow_live is False


def test_build_validation_status_reports_observation_not_live():
    rules = monitor.load_validation_rules("config/paper_validation_rules.yaml")
    status = monitor.build_validation_status(
        monitor_summary=make_monitor_summary(),
        daily_summary=make_daily_summary(),
        rules=rules,
    )
    row = status.iloc[0]

    assert set(monitor.VALIDATION_STATUS_COLUMNS).issubset(status.columns)
    assert row["validation_status"] == "in osservazione"
    assert row["allow_live"] is False or row["allow_live"] == 0
    assert row["ready_for_micro_live"] is False or row["ready_for_micro_live"] == 0
    assert "allow_live=false" in row["observation_reasons"]


def test_build_validation_status_can_report_not_ready():
    rules = monitor.load_validation_rules("config/paper_validation_rules.yaml")
    bad = make_monitor_summary(max_drawdown=13.0, max_losses=10)
    status = monitor.build_validation_status(bad, make_daily_summary(), rules)

    assert status.iloc[0]["validation_status"] == "non pronto"
    assert "drawdown massimo" in status.iloc[0]["fail_reasons"]


def test_validation_script_prints_and_exports(monkeypatch, tmp_path, capsys):
    monitor_path = tmp_path / "paper_monitor_summary.csv"
    validation_path = tmp_path / "paper_validation_status.csv"
    fake_reports = monitor.PaperReports(trades=pd.DataFrame(), equity_curve=pd.DataFrame(), daily_summary=make_daily_summary())

    monkeypatch.setattr(script, "DEFAULT_PAPER_MONITOR_SUMMARY_PATH", monitor_path)
    monkeypatch.setattr(script, "DEFAULT_PAPER_VALIDATION_STATUS_PATH", validation_path)
    monkeypatch.setattr(script, "load_paper_reports", lambda: fake_reports)
    monkeypatch.setattr(script, "build_monitor_summary", lambda _reports, strategy_name: make_monitor_summary())

    script.main()
    output = capsys.readouterr().out

    assert monitor_path.exists()
    assert validation_path.exists()
    assert "Paper Validation Status" in output
    assert "allow_live: False" in output
    assert "No strategy was promoted automatically." in output


def test_validation_sources_are_research_only():
    for path in ["config/paper_validation_rules.yaml", "scripts/check_paper_validation_status.py"]:
        source = open(path, encoding="utf-8").read()
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
