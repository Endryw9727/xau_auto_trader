from pathlib import Path

import pandas as pd
import pytest

from scripts import fetch_yahoo_ohlcv as fetcher


def _payload():
    return {
        "chart": {
            "error": None,
            "result": [
                {
                    "timestamp": [1700000000, 1700003600, 1700007200],
                    "indicators": {
                        "quote": [
                            {
                                "open": [1.10, 1.11, None],
                                "high": [1.12, 1.13, 1.14],
                                "low": [1.09, 1.10, 1.11],
                                "close": [1.11, 1.12, 1.13],
                                "volume": [100, 200, 300],
                            }
                        ]
                    },
                }
            ],
        }
    }


def test_parse_yahoo_chart_builds_clean_frame():
    frame = fetcher.parse_yahoo_chart(_payload())

    # The third row has a null Open and is dropped.
    assert list(frame.columns) == ["Date", "Open", "High", "Low", "Close", "Volume"]
    assert len(frame) == 2
    assert frame["Open"].tolist() == [1.10, 1.11]
    assert pd.api.types.is_datetime64_any_dtype(frame["Date"])


def test_parse_yahoo_chart_errors():
    with pytest.raises(ValueError):
        fetcher.parse_yahoo_chart({"chart": {"error": "Not Found", "result": None}})
    with pytest.raises(ValueError):
        fetcher.parse_yahoo_chart({"chart": {"result": []}})
    with pytest.raises(ValueError):
        fetcher.parse_yahoo_chart({"chart": {"result": [{"timestamp": []}]}})


def test_symbol_mapping_covers_requested_instruments():
    for symbol in ("EURUSD", "AUDUSD", "GBPUSD", "USDJPY", "USDCAD", "NAS100", "XAUUSD"):
        assert symbol in fetcher.YAHOO_SYMBOLS


def test_fetch_ohlcv_unknown_symbol():
    with pytest.raises(KeyError):
        fetcher.fetch_ohlcv("DOGEUSD")


def test_fetch_ohlcv_uses_parser(monkeypatch):
    monkeypatch.setattr(fetcher, "fetch_yahoo_chart_json", lambda *a, **k: _payload())
    frame = fetcher.fetch_ohlcv("EURUSD")
    assert len(frame) == 2


def test_save_ohlcv_csv_roundtrip(tmp_path):
    frame = fetcher.parse_yahoo_chart(_payload())
    path = fetcher.save_ohlcv_csv(frame, tmp_path / "eurusd.csv")
    assert path.exists()
    reloaded = pd.read_csv(path)
    assert len(reloaded) == 2


def test_fetcher_does_not_execute_orders():
    source = Path("scripts/fetch_yahoo_ohlcv.py").read_text(encoding="utf-8")
    assert "order_send" not in source
    assert "v51_demo_executor" not in source
