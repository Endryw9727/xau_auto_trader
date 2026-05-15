from pathlib import Path

import pandas as pd
import pytest
import yaml

from src.market_data.mt5_csv_bridge import (
    import_mt5_csv_bridge,
    import_mt5_csv_timeframe,
    load_mt5_csv_bridge_config,
    load_mt5_export_csv,
)


def write_bridge_config(path: Path, input_dir: Path, archive_dir: Path, *, timeframes=None, auto_import=False):
    path.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "symbol": "XAUUSD",
                "source": "mt5_csv_bridge",
                "allow_live": False,
                "execution_enabled": False,
                "demo_only": True,
                "auto_import": auto_import,
                "input_dir": str(input_dir),
                "archive_dir": str(archive_dir),
                "timeframes": timeframes or {"M15": "xauusd_m15.csv"},
            }
        ),
        encoding="utf-8",
    )


def test_import_valid_csv_removes_duplicates_and_sorts(tmp_path):
    input_dir = tmp_path / "input"
    archive_dir = tmp_path / "archive"
    input_dir.mkdir()
    config_path = tmp_path / "mt5_csv_bridge.yaml"
    write_bridge_config(config_path, input_dir, archive_dir)
    source = input_dir / "xauusd_m15.csv"
    source.write_text(
        "\n".join(
            [
                "Date,Time,Open,High,Low,Close,TickVol,Vol,Spread",
                "2026-05-15,10:30:00,2402,2403,2401,2402.5,120,0,2",
                "2026-05-15,10:00:00,2400,2401,2399,2400.5,100,0,2",
                "2026-05-15,10:15:00,2401,2402,2400,2401.5,110,0,2",
                "2026-05-15,10:15:00,2401,2402.2,2400,2401.7,115,0,2",
            ]
        ),
        encoding="utf-8",
    )

    results = import_mt5_csv_bridge(
        config_path=config_path,
        output_dir=tmp_path / "raw" / "timeframes",
        m15_output_path=tmp_path / "raw" / "xauusd.csv",
    )

    result = results[0]
    assert result.status == "OK"
    assert result.rows_read == 4
    assert result.rows_after == 3
    assert result.added_rows == 3
    main = pd.read_csv(tmp_path / "raw" / "xauusd.csv")
    assert list(main["Date"]) == ["2026-05-15 10:00:00", "2026-05-15 10:15:00", "2026-05-15 10:30:00"]
    assert float(main.loc[1, "Close"]) == 2401.7


def test_bridge_file_missing_and_empty_file_statuses(tmp_path):
    input_dir = tmp_path / "input"
    archive_dir = tmp_path / "archive"
    input_dir.mkdir()
    config_path = tmp_path / "mt5_csv_bridge.yaml"
    write_bridge_config(config_path, input_dir, archive_dir)
    config = load_mt5_csv_bridge_config(config_path)

    missing = import_mt5_csv_timeframe(
        config,
        timeframe="M15",
        source_file=input_dir / "xauusd_m15.csv",
        output_dir=tmp_path / "out",
        m15_output_path=tmp_path / "xauusd.csv",
    )
    assert missing.status == "FILE_MISSING"

    empty_file = input_dir / "xauusd_m15.csv"
    empty_file.write_text("", encoding="utf-8")
    empty = import_mt5_csv_timeframe(
        config,
        timeframe="M15",
        source_file=empty_file,
        output_dir=tmp_path / "out",
        m15_output_path=tmp_path / "xauusd.csv",
    )
    assert empty.status == "EMPTY_FILE"


def test_load_mt5_export_validates_ohlc_and_timeframe(tmp_path):
    bad_ohlc = tmp_path / "bad_ohlc.csv"
    bad_ohlc.write_text(
        "\n".join(
            [
                "Date,Time,Open,High,Low,Close,TickVol,Vol,Spread",
                "2026-05-15,10:00:00,2400,2399,2398,2400.5,100,0,2",
                "2026-05-15,10:15:00,2401,2402,2400,2401.5,110,0,2",
                "2026-05-15,10:30:00,2402,2403,2401,2402.5,120,0,2",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Invalid OHLC"):
        load_mt5_export_csv(bad_ohlc, "M15")

    wrong_tf = tmp_path / "wrong_tf.csv"
    wrong_tf.write_text(
        "\n".join(
            [
                "Date,Time,Open,High,Low,Close,TickVol,Vol,Spread",
                "2026-05-15,10:00:00,2400,2401,2399,2400.5,100,0,2",
                "2026-05-15,10:05:00,2401,2402,2400,2401.5,110,0,2",
                "2026-05-15,10:10:00,2402,2403,2401,2402.5,120,0,2",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="timeframe mismatch"):
        load_mt5_export_csv(wrong_tf, "M15")


def test_bridge_config_guardrails_reject_execution(tmp_path):
    path = tmp_path / "mt5_csv_bridge.yaml"
    write_bridge_config(path, tmp_path / "input", tmp_path / "archive")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["execution_enabled"] = True
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(PermissionError, match="execution_enabled"):
        load_mt5_csv_bridge_config(path)
