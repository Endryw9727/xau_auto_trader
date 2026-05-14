import pandas as pd

from scripts import check_data_freshness as script
from src.market_data.data_freshness import DataFreshnessReport


def make_report(status: str = "OK") -> DataFreshnessReport:
    return DataFreshnessReport(
        symbol="XAUUSD",
        path="data/raw/xauusd.csv",
        status=status,
        reason="latest candle age is acceptable" if status == "OK" else "latest candle is too old",
        latest_timestamp=pd.Timestamp("2026-05-15 10:00"),
        timeframe_minutes=15.0,
        timeframe="15m",
        row_count=100,
        gap_count=0,
        missing_candles=0,
        max_gap_minutes=0.0,
        age_minutes=10.0,
        missing_expected_candle=False,
        market_open=True,
        checked_at=pd.Timestamp("2026-05-15 10:10"),
        error="",
    )


def test_check_data_freshness_script_prints_and_exports(monkeypatch, capsys):
    calls = {"logged": False}
    monkeypatch.setattr(script, "analyze_data_freshness", lambda *_args, **_kwargs: make_report("OK"))

    def fake_append(report):
        calls["logged"] = True
        assert report.status == "OK"

    monkeypatch.setattr(script, "append_freshness_log", fake_append)

    script.main()
    output = capsys.readouterr().out

    assert "Data Freshness Check" in output
    assert "Symbol: XAUUSD" in output
    assert "Timeframe: 15m" in output
    assert "Status: OK" in output
    assert "Reason:" in output
    assert calls["logged"] is True
