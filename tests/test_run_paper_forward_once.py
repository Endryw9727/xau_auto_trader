import pandas as pd

from scripts import run_paper_forward_once as script
from src.paper.paper_forward_engine import ForwardRunResult


def test_run_paper_forward_once_prints_result(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        script,
        "run_preflight_checks",
        lambda: [
            {"name": "live_mode_false", "passed": True, "detail": "ok"},
            {"name": "allow_live_false", "passed": True, "detail": "ok"},
        ],
    )
    raw_path = tmp_path / "xauusd.csv"
    raw_path.write_text("Date,Open,High,Low,Close,Volume\n", encoding="utf-8")
    monkeypatch.setattr(script, "RAW_DATA_PATH", raw_path)
    monkeypatch.setattr(
        script,
        "load_csv_data",
        lambda _path: pd.DataFrame(
            {"Open": [1.0], "High": [1.1], "Low": [0.9], "Close": [1.0], "Volume": [1]},
            index=pd.to_datetime(["2025-01-01"]),
        ),
    )
    monkeypatch.setattr(
        script,
        "run_paper_forward_once",
        lambda _data: ForwardRunResult(
            status="OK",
            decision="NO_TRADE",
            strategy_name="proxy_hardened_no_worst_hours_high_margin",
            reason="no setup",
            equity=1000.0,
            drawdown_pct=0.0,
            daily_loss_pct=0.0,
            open_trades=0,
            next_action="continue",
        ),
    )

    script.main()
    output = capsys.readouterr().out

    assert "Paper Forward Once" in output
    assert "Signal: NO_TRADE" in output
    assert "allow_live remains false" in output


def test_run_paper_forward_once_stops_on_failed_preflight(monkeypatch, capsys):
    monkeypatch.setattr(
        script,
        "run_preflight_checks",
        lambda: [{"name": "monitor_status", "passed": False, "detail": "STOP"}],
    )

    script.main()
    output = capsys.readouterr().out

    assert "Preflight status: FAIL" in output
    assert "Decision: STOP" in output
