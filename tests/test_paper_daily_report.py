import pandas as pd

from scripts import paper_daily_report as script


def test_paper_daily_report_script_prints_status(monkeypatch, tmp_path, capsys):
    summary_path = tmp_path / "paper_monitor_summary.csv"
    fake_summary = pd.DataFrame(
        [
            {
                "strategy_name": "proxy_hardened_no_worst_hours",
                "report_as_of": "2025-01-08",
                "status": "WARNING",
                "warning_reasons": "drawdown 9.00% > 8%",
                "stop_reasons": "",
                "equity_current": 1200.0,
                "total_profit_loss": 200.0,
                "current_drawdown_eur": 0.0,
                "current_drawdown_pct": 0.0,
                "max_drawdown_eur": 90.0,
                "max_drawdown_pct": 9.0,
                "total_trades": 80,
                "trades_today": 1,
                "trades_week": 3,
                "trades_month": 20,
                "profit_factor_total": 1.3,
                "profit_factor_last_30": 1.2,
                "profit_factor_last_50": 1.1,
                "win_rate_total": 40.0,
                "win_rate_last_30": 42.0,
                "max_consecutive_losses": 6,
                "current_consecutive_losses": 0,
                "daily_loss_current": 0.0,
                "daily_loss_current_pct": 0.0,
                "weekly_loss_current": 0.0,
                "weekly_loss_current_pct": 0.0,
                "total_no_trade_days": 5,
                "current_no_trade_days": 0,
                "last_trade_time": "2025-01-08 09:00:00",
                "last_entry_reason": "test reason",
                "last_session": "LONDON",
                "last_result": "WIN",
            }
        ]
    )

    monkeypatch.setattr(script, "DEFAULT_PAPER_MONITOR_SUMMARY_PATH", summary_path)
    monkeypatch.setattr(script, "load_paper_reports", lambda: object())
    monkeypatch.setattr(script, "build_monitor_summary", lambda _reports, strategy_name: fake_summary)

    script.main()
    output = capsys.readouterr().out

    assert summary_path.exists()
    assert "Paper Daily Report" in output
    assert "Status: WARNING" in output
    assert "WARNING reasons" in output
    assert "No live trading was enabled." in output


def test_paper_daily_report_source_is_research_only():
    source = open("scripts/paper_daily_report.py", encoding="utf-8").read()
    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
