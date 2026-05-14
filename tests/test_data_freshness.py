from pathlib import Path

import pandas as pd

from src.market_data.data_freshness import (
    analyze_data_freshness,
    append_freshness_log,
    classify_freshness_status,
    detect_timeframe_minutes,
    find_temporal_gaps,
)


def write_ohlcv(path: Path, timestamps: list[pd.Timestamp]) -> None:
    rows = ["Date,Open,High,Low,Close,Volume"]
    for timestamp in timestamps:
        rows.append(f"{timestamp:%Y-%m-%d %H:%M:%S},1,2,0.5,1.5,1")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_analyze_data_freshness_ok_for_recent_15m_csv(tmp_path):
    path = tmp_path / "xauusd.csv"
    timestamps = pd.date_range("2026-05-14 09:00", periods=5, freq="15min")
    write_ohlcv(path, list(timestamps))

    report = analyze_data_freshness(path, now=pd.Timestamp("2026-05-14 10:05"))

    assert report.status == "OK"
    assert report.timeframe == "15m"
    assert report.row_count == 5
    assert report.age_minutes == 5.0
    assert report.gap_count == 0


def test_analyze_data_freshness_warning_and_stale(tmp_path):
    path = tmp_path / "xauusd.csv"
    timestamps = pd.date_range("2026-05-14 09:00", periods=5, freq="15min")
    write_ohlcv(path, list(timestamps))

    warning = analyze_data_freshness(path, now=pd.Timestamp("2026-05-14 10:55"))
    stale = analyze_data_freshness(path, now=pd.Timestamp("2026-05-14 12:00"))

    assert warning.status == "WARNING"
    assert stale.status == "STALE"
    assert stale.missing_expected_candle is True


def test_detects_temporal_gaps_and_missing_candles(tmp_path):
    path = tmp_path / "xauusd.csv"
    timestamps = [
        pd.Timestamp("2026-05-14 09:00"),
        pd.Timestamp("2026-05-14 09:15"),
        pd.Timestamp("2026-05-14 10:00"),
    ]
    write_ohlcv(path, timestamps)

    report = analyze_data_freshness(path, now=pd.Timestamp("2026-05-14 10:05"))

    assert report.gap_count == 1
    assert report.missing_candles == 2
    assert report.max_gap_minutes == 45.0


def test_missing_file_returns_error(tmp_path):
    report = analyze_data_freshness(tmp_path / "missing.csv", now=pd.Timestamp("2026-05-14 10:00"))

    assert report.status == "ERROR"
    assert "missing" in report.error


def test_freshness_log_is_exported(tmp_path):
    path = tmp_path / "xauusd.csv"
    log_path = tmp_path / "freshness.csv"
    timestamps = pd.date_range("2026-05-14 09:00", periods=2, freq="15min")
    write_ohlcv(path, list(timestamps))
    report = analyze_data_freshness(path, now=pd.Timestamp("2026-05-14 09:20"))

    append_freshness_log(report, log_path)
    exported = pd.read_csv(log_path)

    assert log_path.exists()
    assert exported.iloc[0]["status"] == "OK"
    assert exported.iloc[0]["symbol"] == "XAUUSD"


def test_helpers_classify_timeframe_and_status():
    index = pd.date_range("2026-05-14 09:00", periods=4, freq="15min")

    assert detect_timeframe_minutes(index) == 15.0
    assert find_temporal_gaps(index, 15) == []
    assert classify_freshness_status(20, market_open=True) == "OK"
    assert classify_freshness_status(60, market_open=True) == "WARNING"
    assert classify_freshness_status(120, market_open=True) == "STALE"
