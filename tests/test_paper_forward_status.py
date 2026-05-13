from scripts import paper_forward_status as script


def test_paper_forward_status_prints(monkeypatch, capsys):
    monkeypatch.setattr(
        script,
        "build_forward_status",
        lambda: {
            "strategy_name": "proxy_hardened_no_worst_hours_high_margin",
            "status": "OK",
            "equity": 1000.0,
            "open_trades_count": 0,
            "closed_trades_count": 2,
            "total_pnl": 12.0,
            "today_pnl": 4.0,
            "profit_factor": 1.5,
            "drawdown_pct": 2.0,
            "loss_streak": 0,
            "max_loss_streak": 1,
            "can_continue_tomorrow": True,
            "stop_reason": "",
            "warning_reason": "",
        },
    )

    script.main()
    output = capsys.readouterr().out

    assert "Paper Forward Status" in output
    assert "Tomorrow: CONTINUE" in output
    assert "allow_live remains false" in output
