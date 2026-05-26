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

    def __init__(self, *, empty_timeframes=None):
        self.initialized = False
        self.empty_timeframes = set(empty_timeframes or [])
        self.selected = []
        self._last_error = "OK"

    def initialize(self):
        self.initialized = True
        return True

    def shutdown(self):
        self.initialized = False

    def terminal_info(self):
        return SimpleNamespace(connected=True)

    def account_info(self):
        return SimpleNamespace(login=12345)

    def symbol_select(self, symbol, enable):
        self.selected.append((symbol, enable))
        return True

    def last_error(self):
        return self._last_error

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        if timeframe in self.empty_timeframes:
            self._last_error = f"no history for timeframe {timeframe}"
            return []
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

    def copy_rates_from(self, symbol, timeframe, date_from, count):
        if timeframe in self.empty_timeframes:
            self._last_error = f"copy_rates_from empty for timeframe {timeframe}"
            return []
        return self.copy_rates_from_pos(symbol, timeframe, 0, count)

    def copy_rates_range(self, symbol, timeframe, start, end):
        if timeframe in self.empty_timeframes:
            self._last_error = f"copy_rates_range empty for timeframe {timeframe}"
            return []
        return self.copy_rates_from_pos(symbol, timeframe, 0, 5)


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


def test_mt5_timeframe_update_m15_fallback_da_primary_csv(tmp_path):
    write_timeframe_csv(
        tmp_path / "data" / "xauusd.csv",
        [
            {"Date": "2026-05-26 11:30:00", "Open": 2400.0, "High": 2400.5, "Low": 2399.5, "Close": 2400.2, "Volume": 1},
            {"Date": "2026-05-26 11:45:00", "Open": 2401.0, "High": 2401.5, "Low": 2400.5, "Close": 2401.2, "Volume": 1},
        ],
    )

    result = updater.run_mt5_timeframe_update(
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "diagnostics",
        timeframes=("M15",),
        now=NOW,
        mt5_module=FakeMT5(empty_timeframes={15}),
    )

    summary = pd.read_csv(result.summary_path)
    assert summary.iloc[0]["update_status"] == "OK_FALLBACK_PRIMARY_M15"
    assert str(summary.iloc[0]["fallback_used"]).lower() == "true"
    assert str(summary.iloc[0]["updated"]).lower() == "true"
    assert (tmp_path / "data" / "timeframes" / "XAUUSD_M15.csv").exists()


def test_mt5_timeframe_update_m1_no_candles_warning_non_aggiorna(tmp_path):
    old_file = tmp_path / "data" / "timeframes" / "XAUUSD_M1.csv"
    write_timeframe_csv(
        old_file,
        [{"Date": "2026-05-26 11:59:00", "Open": 2400.0, "High": 2400.5, "Low": 2399.5, "Close": 2400.2, "Volume": 1}],
    )
    before = old_file.read_text(encoding="utf-8")

    result = updater.run_mt5_timeframe_update(
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "diagnostics",
        timeframes=("M1",),
        now=NOW,
        mt5_module=FakeMT5(empty_timeframes={1}),
    )

    summary = pd.read_csv(result.summary_path)
    assert summary.iloc[0]["update_status"] == "WARNING_NO_MT5_CANDLES"
    assert str(summary.iloc[0]["updated"]).lower() == "false"
    assert old_file.read_text(encoding="utf-8") == before


def test_mt5_timeframe_update_m5_no_candles_warning_non_aggiorna(tmp_path):
    old_file = tmp_path / "data" / "timeframes" / "XAUUSD_M5.csv"
    write_timeframe_csv(
        old_file,
        [{"Date": "2026-05-26 11:55:00", "Open": 2400.0, "High": 2400.5, "Low": 2399.5, "Close": 2400.2, "Volume": 1}],
    )
    before = old_file.read_text(encoding="utf-8")

    result = updater.run_mt5_timeframe_update(
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "diagnostics",
        timeframes=("M5",),
        now=NOW,
        mt5_module=FakeMT5(empty_timeframes={5}),
    )

    summary = pd.read_csv(result.summary_path)
    assert summary.iloc[0]["update_status"] == "WARNING_NO_MT5_CANDLES"
    assert str(summary.iloc[0]["updated"]).lower() == "false"
    assert old_file.read_text(encoding="utf-8") == before


def test_mt5_timeframe_update_m30_h1_h4_aggiornati_normalmente(tmp_path):
    result = updater.run_mt5_timeframe_update(
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "diagnostics",
        timeframes=("M30", "H1", "H4"),
        now=NOW,
        mt5_module=FakeMT5(),
    )

    summary = pd.read_csv(result.summary_path)
    assert set(summary["timeframe"]) == {"M30", "H1", "H4"}
    assert set(summary["update_status"]) == {"OK"}
    assert (summary["candles_returned"] > 0).all()
    assert set(summary["method_used"]) == {"copy_rates_from_pos"}


def test_mt5_timeframe_update_last_error_scritto_nel_report(tmp_path):
    result = updater.run_mt5_timeframe_update(
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "diagnostics",
        timeframes=("M1",),
        now=NOW,
        mt5_module=FakeMT5(empty_timeframes={1}),
    )

    summary = pd.read_csv(result.summary_path)
    latest = result.latest_path.read_text(encoding="utf-8")
    assert "copy_rates_range empty" in summary.iloc[0]["mt5_last_error"]
    assert "mt5_last_error=" in latest


def test_mt5_timeframe_update_non_invia_ordini():
    source = open("scripts/update_mt5_timeframes.py", encoding="utf-8").read()

    assert "order_send" not in source
    assert "TRADE_ACTION_DEAL" not in source
