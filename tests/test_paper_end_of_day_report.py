import pandas as pd

from scripts import paper_end_of_day_report as script
from src.paper.paper_candidate import load_paper_candidate_config
from src.paper.paper_monitor import PaperReports


def make_monitor(
    status: str = "OK",
    pf_50: float = 1.4,
    max_dd: float = 7.0,
    daily_loss: float = 0.0,
    weekly_loss: float = 0.0,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "strategy_name": "proxy_hardened_no_worst_hours_high_margin",
                "report_as_of": "2026-05-07",
                "status": status,
                "equity_current": 2134.0,
                "current_drawdown_pct": 0.0,
                "max_drawdown_pct": max_dd,
                "profit_factor_total": 1.409,
                "profit_factor_last_30": 1.497,
                "profit_factor_last_50": pf_50,
                "current_consecutive_losses": 0,
                "max_consecutive_losses": 10,
                "daily_loss_current_pct": daily_loss,
                "weekly_loss_current_pct": weekly_loss,
            }
        ]
    )


def make_reports() -> PaperReports:
    trades = pd.DataFrame(
        {
            "strategy_name": ["proxy_hardened_no_worst_hours_high_margin"] * 2,
            "entry_time": pd.to_datetime(["2026-05-07 10:00:00", "2026-05-06 10:00:00"]),
            "pnl_eur": [12.0, -5.0],
        }
    )
    return PaperReports(trades=trades, equity_curve=pd.DataFrame(), daily_summary=pd.DataFrame())


def test_continuation_decision_continue_and_pause():
    config = load_paper_candidate_config("config/paper_candidate.yaml")
    continue_decision, _ = script.continuation_decision(make_monitor().iloc[0], config)
    pause_decision, reasons = script.continuation_decision(make_monitor(pf_50=0.99).iloc[0], config)

    assert continue_decision == "CONTINUE"
    assert pause_decision == "PAUSE"
    assert any("PF last 50" in reason for reason in reasons)


def test_eod_todays_trades_and_pnl():
    trades, pnl = script.todays_trades_and_pnl(
        make_reports().trades,
        "proxy_hardened_no_worst_hours_high_margin",
        "2026-05-07",
    )

    assert trades == 1
    assert pnl == 12.0


def test_paper_end_of_day_report_script_prints(monkeypatch, capsys):
    monkeypatch.setattr(script, "load_paper_candidate_config", lambda: load_paper_candidate_config("config/paper_candidate.yaml"))
    monkeypatch.setattr(script, "load_paper_reports", make_reports)
    monkeypatch.setattr(script, "build_monitor_summary", lambda _reports, strategy_name: make_monitor())

    script.main()
    output = capsys.readouterr().out

    assert "Paper End Of Day Report" in output
    assert "Paper main strategy: proxy_hardened_no_worst_hours_high_margin" in output
    assert "Tomorrow decision: CONTINUE" in output
    assert "allow_live remains false" in output


def test_paper_end_of_day_sources_are_research_only():
    source = open("scripts/paper_end_of_day_report.py", encoding="utf-8").read()
    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
