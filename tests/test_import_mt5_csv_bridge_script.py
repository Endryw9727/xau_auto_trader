import pandas as pd

from scripts import import_mt5_csv_bridge as script
from src.market_data.mt5_csv_bridge import MT5CsvBridgeResult


def test_import_mt5_csv_bridge_script_prints_results(monkeypatch, capsys):
    monkeypatch.setattr(
        script,
        "import_mt5_csv_bridge",
        lambda: [
            MT5CsvBridgeResult(
                symbol="XAUUSD",
                timeframe="M15",
                source_file="data/mt5_bridge/input/xauusd_m15.csv",
                output_file="data/raw/xauusd.csv",
                rows_read=3,
                rows_before=100,
                rows_after=103,
                added_rows=3,
                last_timestamp_before=pd.Timestamp("2026-05-15 09:45"),
                last_timestamp_after=pd.Timestamp("2026-05-15 10:30"),
                status="OK",
                reason="imported",
            )
        ],
    )

    script.main()
    output = capsys.readouterr().out

    assert "MT5 CSV Bridge Import" in output
    assert "Timeframe: M15" in output
    assert "Status: OK" in output
    assert "scripts/check_data_freshness.py" in output
