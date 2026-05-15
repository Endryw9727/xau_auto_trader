from pathlib import Path

from src.market_data.mt5_csv_bridge import load_mt5_csv_bridge_config


def test_mt5_csv_bridge_config_keeps_execution_disabled():
    config = load_mt5_csv_bridge_config("config/mt5_csv_bridge.yaml")

    assert config.demo_only is True
    assert config.allow_live is False
    assert config.execution_enabled is False
    assert config.auto_import is False


def test_mt5_csv_bridge_source_has_no_execution_references():
    source = Path("src/market_data/mt5_csv_bridge.py").read_text(encoding="utf-8")

    assert "place_order" not in source
    assert "OrderSend" not in source
    assert "CTrade" not in source
    assert "live_broker" not in source
    assert "MetaTrader5" not in source
