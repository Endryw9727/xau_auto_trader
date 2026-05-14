import pandas as pd

from scripts import paper_preflight_check as script
from src.market_data.data_freshness import DataFreshnessReport


def freshness(status: str) -> DataFreshnessReport:
    return DataFreshnessReport(
        symbol="XAUUSD",
        path="data/raw/xauusd.csv",
        status=status,
        reason=f"{status} test reason",
        latest_timestamp=pd.Timestamp("2026-05-15 10:00") if status != "ERROR" else None,
        timeframe_minutes=15.0 if status != "ERROR" else None,
        timeframe="15m" if status != "ERROR" else "unknown",
        row_count=10 if status != "ERROR" else 0,
        gap_count=0,
        missing_candles=0,
        max_gap_minutes=0.0,
        age_minutes=10.0 if status == "OK" else 60.0 if status == "WARNING" else None if status == "ERROR" else 120.0,
        missing_expected_candle=status == "STALE",
        market_open=True,
        checked_at=pd.Timestamp("2026-05-15 10:10"),
        error="file missing" if status == "ERROR" else "",
    )


def test_preflight_status_pass_warning_stale_and_fail():
    assert script.preflight_status([{"name": "data_freshness", "passed": True, "detail": "OK", "status": "OK"}]) == "PASS"
    assert (
        script.preflight_status(
            [{"name": "data_freshness", "passed": True, "detail": "WARNING", "status": "WARNING"}]
        )
        == "WARNING"
    )
    assert (
        script.preflight_status(
            [{"name": "data_freshness", "passed": False, "detail": "STALE", "status": "STALE"}]
        )
        == "STALE"
    )
    assert (
        script.preflight_status(
            [{"name": "data_freshness", "passed": False, "detail": "ERROR", "status": "ERROR"}]
        )
        == "FAIL"
    )


def test_preflight_check_marks_stale_data_as_failed(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("trading:\n  live_mode: false\n", encoding="utf-8")
    reports_dir = tmp_path / "paper"
    reports_dir.mkdir()

    monkeypatch.setattr(script, "CONFIG_PATH", config_path)
    monkeypatch.setattr(script, "DEFAULT_PAPER_OUTPUT_DIR", reports_dir)
    monkeypatch.setenv("LIVE_MODE", "false")
    monkeypatch.setattr(script, "analyze_data_freshness", lambda *_args, **_kwargs: freshness("STALE"))
    monkeypatch.setattr(script, "append_freshness_log", lambda _report: None)
    monkeypatch.setattr(script, "load_paper_reports", lambda: object())
    monkeypatch.setattr(
        script,
        "build_monitor_summary",
        lambda _reports, strategy_name: pd.DataFrame([{"status": "OK", "warning_reasons": "", "stop_reasons": ""}]),
    )

    checks = script.run_preflight_checks()
    data_check = next(item for item in checks if item["name"] == "data_freshness")

    assert data_check["passed"] is False
    assert data_check["status"] == "STALE"
    assert "reason=" in data_check["detail"]
