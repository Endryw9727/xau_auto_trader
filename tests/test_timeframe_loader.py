import pandas as pd

from src.market_data.timeframe_loader import (
    detect_csv_separator,
    detect_header_or_no_header,
    load_timeframe_csv,
    load_xauusd_timeframes,
    normalize_ohlc_columns,
)


def test_detects_tab_separator_and_no_header(tmp_path):
    path = tmp_path / "XAUUSD_M5.csv"
    path.write_text(
        "2026-01-01 09:00\t2350.0\t2351.0\t2349.0\t2350.5\t5\n"
        "2026-01-01 09:05\t2350.5\t2352.0\t2350.0\t2351.5\t5\n",
        encoding="utf-8",
    )

    assert detect_csv_separator(path) == "\t"
    assert detect_header_or_no_header(path) == "no_header"


def test_load_timeframe_csv_without_header_uses_neutral_volume_for_timeframe_code(tmp_path):
    path = tmp_path / "XAUUSD_M15.csv"
    path.write_text(
        "2026-01-01 09:00\t2350.0\t2351.0\t2349.0\t2350.5\t15\n"
        "2026-01-01 09:15\t2350.5\t2352.0\t2350.0\t2351.5\t15\n",
        encoding="utf-8",
    )

    data = load_timeframe_csv(path, "M15")

    assert list(data.columns) == [
        "time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "timeframe",
        "has_real_volume",
        "timeframe_code",
    ]
    assert len(data) == 2
    assert data["volume"].tolist() == [1.0, 1.0]
    assert data["has_real_volume"].tolist() == [False, False]
    assert data["timeframe_code"].tolist() == [15, 15]
    assert data["timeframe"].tolist() == ["M15", "M15"]


def test_normalize_ohlc_columns_with_header_aliases():
    raw = pd.DataFrame(
        {
            "DateTime": ["2026-01-01 09:00"],
            "Open": [2350.0],
            "High": [2351.0],
            "Low": [2349.0],
            "Close": [2350.5],
            "Volume": [123],
        }
    )

    normalized = normalize_ohlc_columns(raw)

    assert {"time", "open", "high", "low", "close", "volume"}.issubset(normalized.columns)


def test_load_timeframe_csv_preserves_real_volume_when_not_timeframe_code(tmp_path):
    path = tmp_path / "XAUUSD_M5.csv"
    path.write_text(
        "time,open,high,low,close,volume\n"
        "2026-01-01 09:00,2350.0,2351.0,2349.0,2350.5,100\n"
        "2026-01-01 09:05,2350.5,2352.0,2350.0,2351.5,130\n",
        encoding="utf-8",
    )

    data = load_timeframe_csv(path, "M5")

    assert "timeframe_code" not in data.columns
    assert data["volume"].tolist() == [100, 130]
    assert data["has_real_volume"].tolist() == [True, True]


def test_load_xauusd_timeframes_loads_required_files(tmp_path):
    rows = {
        "M1": "2026-01-01 09:00\t2350\t2351\t2349\t2350.5\t1\n",
        "M5": "2026-01-01 09:00\t2350\t2351\t2349\t2350.5\t5\n",
        "M15": "2026-01-01 09:00\t2350\t2351\t2349\t2350.5\t15\n",
        "M30": "2026-01-01 09:00\t2350\t2351\t2349\t2350.5\t30\n",
        "H1": "2026-01-01 09:00\t2350\t2351\t2349\t2350.5\t60\n",
        "H4": "2026-01-01 08:00\t2350\t2351\t2349\t2350.5\t240\n",
    }

    for timeframe, content in rows.items():
        (tmp_path / f"XAUUSD_{timeframe}.csv").write_text(content, encoding="utf-8")

    frames = load_xauusd_timeframes(tmp_path)

    assert set(frames) == {"M1", "M5", "M15", "M30", "H1", "H4"}
    assert all(not frame.empty for frame in frames.values())
    assert all(frame["has_real_volume"].eq(False).all() for frame in frames.values())

