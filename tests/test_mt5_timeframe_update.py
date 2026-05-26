from types import SimpleNamespace

import pandas as pd

from scripts import update_mt5_timeframes as updater


NOW = pd.Timestamp("2026-05-26 12:00:00")


class FakeMT5:
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240

    def __init__(self):
        self.initialized = False

    def initialize(self):
        self.initialized = True
        return True

    def shutdown(self):
        self.initialized = False

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        index = pd.date_range(end=NOW, periods=5, freq="1min")
        return [
            {
                "time": int(timestamp.timestamp()),
                "open": 2400.0 + position,
                "high": 2400.5 + position,
                "low": 2399.5 + position,
                "close": 2400.2 + position,
                "tick_volume": 1000,
            }
            for position, timestamp in enumerate(index)
        ]


def write_timeframe_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_mt5_timeframe_update_gestisce_file_mancanti(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "import_mt5_module", lambda: None)

    result = updater.run_mt5_timeframe_update(data_dir=tmp_path / "data", output_dir=tmp_path / "diagnostics", timeframes=("M1",), now=NOW)

    summary = pd.read_csv(result.summary_path)
    assert summary.iloc[0]["update_status"] == "WARNING"
    assert summary.iloc[0]["validation_status"] == "MISSING"


def test_mt5_timeframe_update_gestisce_csv_vuoti(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "import_mt5_module", lambda: None)
    path = tmp_path / "data" / "timeframes" / "XAUUSD_M1.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")

    result = updater.run_mt5_timeframe_update(data_dir=tmp_path / "data", output_dir=tmp_path / "diagnostics", timeframes=("M1",), now=NOW)

    summary = pd.read_csv(result.summary_path)
    assert summary.iloc[0]["validation_status"] == "EMPTY"


def test_mt5_timeframe_update_gestisce_colonne_mancanti(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "import_mt5_module", lambda: None)
    write_timeframe_csv(
        tmp_path / "data" / "timeframes" / "XAUUSD_M1.csv",
        [{"Date": "2026-05-26 11:59:00", "Open": 2400.0, "Close": 2400.2}],
    )

    result = updater.run_mt5_timeframe_update(data_dir=tmp_path / "data", output_dir=tmp_path / "diagnostics", timeframes=("M1",), now=NOW)

    summary = pd.read_csv(result.summary_path)
    assert summary.iloc[0]["validation_status"] == "INVALID_COLUMNS"


def test_mt5_timeframe_update_valida_timestamp_ordinati(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "import_mt5_module", lambda: None)
    write_timeframe_csv(
        tmp_path / "data" / "timeframes" / "XAUUSD_M1.csv",
        [
            {"Date": "2026-05-26 12:00:00", "Open": 2401.0, "High": 2401.5, "Low": 2400.5, "Close": 2401.2, "Volume": 1},
            {"Date": "2026-05-26 11:59:00", "Open": 2400.0, "High": 2400.5, "Low": 2399.5, "Close": 2400.2, "Volume": 1},
        ],
    )

    result = updater.run_mt5_timeframe_update(data_dir=tmp_path / "data", output_dir=tmp_path / "diagnostics", timeframes=("M1",), now=NOW)

    summary = pd.read_csv(result.summary_path)
    assert summary.iloc[0]["validation_status"] == "INVALID_TIMESTAMP_ORDER"
    assert str(summary.iloc[0]["timestamp_ordered"]).lower() == "false"


def test_mt5_timeframe_update_produce_report_summary(tmp_path):
    result = updater.run_mt5_timeframe_update(
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "diagnostics",
        timeframes=("M1",),
        now=NOW,
        mt5_module=FakeMT5(),
    )

    summary = pd.read_csv(result.summary_path)
    latest = result.latest_path.read_text(encoding="utf-8")
    assert result.summary_path.exists()
    assert result.latest_path.exists()
    assert summary.iloc[0]["update_status"] == "OK"
    assert summary.iloc[0]["validation_status"] == "OK"
    assert "M1:" in latest


def test_mt5_timeframe_update_non_invia_ordini():
    source = open("scripts/update_mt5_timeframes.py", encoding="utf-8").read()

    assert "order_send" not in source
    assert "TRADE_ACTION_DEAL" not in source
