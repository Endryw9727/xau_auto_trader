import yaml

from scripts import paper_preflight_check as script


def test_preflight_checks_mt5_csv_bridge_safe_config():
    check = script.check_mt5_csv_bridge_config(script.DEFAULT_MT5_CSV_BRIDGE_CONFIG_PATH)

    assert check["passed"] is True
    assert check["status"] == "OK"
    assert "allow_live=False" in check["detail"]
    assert "execution_enabled=False" in check["detail"]


def test_preflight_rejects_mt5_csv_bridge_auto_import(tmp_path):
    path = tmp_path / "mt5_csv_bridge.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "symbol": "XAUUSD",
                "source": "mt5_csv_bridge",
                "allow_live": False,
                "execution_enabled": False,
                "demo_only": True,
                "auto_import": True,
                "input_dir": "data/mt5_bridge/input",
                "archive_dir": "data/mt5_bridge/archive",
                "timeframes": {"M15": "xauusd_m15.csv"},
            }
        ),
        encoding="utf-8",
    )

    check = script.check_mt5_csv_bridge_config(path)

    assert check["passed"] is False
    assert check["status"] == "ERROR"
    assert "auto_import=true" in check["detail"]
