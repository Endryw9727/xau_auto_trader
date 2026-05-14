from scripts import run_paper_forward_once as script
from src.paper.paper_forward_engine import ForwardRunResult


def paused_result(reason: str) -> ForwardRunResult:
    return ForwardRunResult(
        status="WARNING",
        decision="PAUSE",
        strategy_name="proxy_hardened_no_worst_hours_high_margin",
        reason=reason,
        equity=1000.0,
        drawdown_pct=0.0,
        daily_loss_pct=0.0,
        open_trades=0,
        next_action="update local XAUUSD data before paper-forward",
    )


def test_run_paper_forward_once_pauses_on_stale_data(monkeypatch, capsys):
    calls = {"load_data": 0, "engine": 0}

    monkeypatch.setattr(
        script,
        "run_preflight_checks",
        lambda: [
            {"name": "live_mode_false", "passed": True, "detail": "ok"},
            {
                "name": "data_freshness",
                "passed": False,
                "detail": "STALE: last=2026-05-07, age=10000 min",
                "status": "STALE",
            },
        ],
    )

    def fail_load(_path):
        calls["load_data"] += 1
        raise AssertionError("market data should not be loaded when data is stale")

    def fail_engine(_data):
        calls["engine"] += 1
        raise AssertionError("paper-forward engine should not run when data is stale")

    monkeypatch.setattr(script, "load_csv_data", fail_load)
    monkeypatch.setattr(script, "run_paper_forward_once", fail_engine)
    monkeypatch.setattr(script, "record_paper_forward_pause", lambda reason: paused_result(reason))

    script.main()
    output = capsys.readouterr().out

    assert "Signal: PAUSE" in output
    assert "Reason: DATA_STALE" in output
    assert "update local XAUUSD data" in output
    assert calls == {"load_data": 0, "engine": 0}


def test_run_paper_forward_once_pauses_on_data_error(monkeypatch, capsys):
    monkeypatch.setattr(
        script,
        "run_preflight_checks",
        lambda: [
            {
                "name": "data_freshness",
                "passed": False,
                "detail": "ERROR: file missing",
                "status": "ERROR",
            },
        ],
    )
    monkeypatch.setattr(script, "record_paper_forward_pause", lambda reason: paused_result(reason))

    script.main()
    output = capsys.readouterr().out

    assert "Signal: PAUSE" in output
    assert "Reason: DATA_ERROR" in output
