import pandas as pd

from scripts import update_market_data_mt5_readonly as script
from src.market_data.mt5_readonly_data_updater import MT5DataUpdateResult


def test_update_market_data_script_prints_safe_unavailable_status(monkeypatch, capsys):
    monkeypatch.setattr(
        script,
        "update_market_data_from_mt5_readonly",
        lambda: [
            MT5DataUpdateResult(
                symbol="XAUUSD",
                timeframe="M15",
                rows_before=100,
                rows_after=100,
                last_timestamp_before=pd.Timestamp("2026-05-07 20:45"),
                last_timestamp_after=pd.Timestamp("2026-05-07 20:45"),
                added_rows=0,
                status="MT5_NOT_AVAILABLE",
                reason="MetaTrader5 package is not installed",
            )
        ],
    )

    script.main()
    output = capsys.readouterr().out

    assert "MT5 Read-Only Market Data Update" in output
    assert "Status: MT5_NOT_AVAILABLE" in output
    assert "No trades were opened" in output
    assert "scripts/check_data_freshness.py" in output
