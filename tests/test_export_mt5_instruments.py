from pathlib import Path

import pandas as pd
import pytest

from scripts import export_mt5_instruments as exporter


class FakeMT5:
    TIMEFRAME_M15 = 15

    def __init__(self, *, rates_by_symbol=None, initialized=True):
        self.rates_by_symbol = rates_by_symbol or {}
        self.initialized = initialized
        self.selected = []
        self.order_send_called = False  # must never be touched

    def initialize(self):
        return self.initialized

    def shutdown(self):
        return None

    def symbol_select(self, symbol, enable):
        self.selected.append((symbol, enable))
        return True

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        return self.rates_by_symbol.get(symbol)

    def last_error(self):
        return "fake"


def _rates(n=120, start_price=100.0):
    base = 1_700_000_000
    rates = []
    price = start_price
    for i in range(n):
        rates.append(
            {"time": base + i * 900, "open": price, "high": price + 0.5, "low": price - 0.5,
             "close": price + 0.1, "tick_volume": 10}
        )
        price += 0.1
    return rates


def test_rates_to_project_frame():
    frame = exporter.rates_to_project_frame(_rates(5))
    assert list(frame.columns) == ["Date", "Open", "High", "Low", "Close", "Volume"]
    assert len(frame) == 5
    assert pd.api.types.is_datetime64_any_dtype(frame["Date"])


def test_rates_to_project_frame_rejects_bad_input():
    with pytest.raises(ValueError):
        exporter.rates_to_project_frame([])
    with pytest.raises(ValueError):
        exporter.rates_to_project_frame([{"time": 1, "open": 1}])  # missing columns


def test_export_writes_csv_per_symbol(tmp_path):
    mt5 = FakeMT5(rates_by_symbol={"EURUSD": _rates(), "XAUUSD-P": _rates(start_price=2000.0)})
    result = exporter.export_instruments(
        ["EURUSD", "XAUUSD"], timeframe="M15", bars=200,
        data_dir=tmp_path / "raw", output_dir=tmp_path / "out", mt5_module=mt5,
    )

    assert result.status == "OK"
    assert (tmp_path / "raw" / "eurusd.csv").exists()
    assert (tmp_path / "raw" / "xauusd.csv").exists()
    eur = pd.read_csv(tmp_path / "raw" / "eurusd.csv")
    assert list(eur.columns) == ["Date", "Open", "High", "Low", "Close", "Volume"]
    assert mt5.order_send_called is False


def test_export_keeps_previous_file_on_missing_symbol(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir(parents=True)
    (raw / "gbpusd.csv").write_text("Date,Open,High,Low,Close,Volume\n2025-01-01,1,1,1,1,1\n", encoding="utf-8")
    mt5 = FakeMT5(rates_by_symbol={})  # returns None for every symbol

    result = exporter.export_instruments(
        ["GBPUSD"], data_dir=raw, output_dir=tmp_path / "out", mt5_module=mt5
    )

    summary = pd.read_csv(result.summary_path)
    assert summary.iloc[0]["status"] == "WARNING"
    # Previous file is untouched.
    assert (raw / "gbpusd.csv").read_text(encoding="utf-8").startswith("Date,Open")


def test_export_mt5_unavailable(tmp_path):
    result = exporter.export_instruments(
        ["EURUSD"], data_dir=tmp_path / "raw", output_dir=tmp_path / "out", mt5_module=None
    )
    assert result.status == "MT5_NOT_AVAILABLE"
    summary = pd.read_csv(result.summary_path)
    assert summary.iloc[0]["status"] == "MT5_NOT_AVAILABLE"


def test_export_not_initialized(tmp_path):
    mt5 = FakeMT5(initialized=False)
    result = exporter.export_instruments(
        ["EURUSD"], data_dir=tmp_path / "raw", output_dir=tmp_path / "out", mt5_module=mt5
    )
    assert result.status == "ERROR"


def test_broker_map_override(tmp_path):
    mt5 = FakeMT5(rates_by_symbol={"US100": _rates()})
    result = exporter.export_instruments(
        ["NAS100"], broker_map={"NAS100": "US100"},
        data_dir=tmp_path / "raw", output_dir=tmp_path / "out", mt5_module=mt5,
    )
    assert result.status == "OK"
    assert ("US100", True) in mt5.selected
    assert (tmp_path / "raw" / "nas100.csv").exists()


def test_parse_map():
    assert exporter._parse_map(["EURUSD=EURUSD.r", "NAS100=US100"]) == {"EURUSD": "EURUSD.r", "NAS100": "US100"}


def test_exporter_does_not_execute_orders():
    source = Path("scripts/export_mt5_instruments.py").read_text(encoding="utf-8")
    assert "order_send" not in source
    assert "v51_demo_executor" not in source
