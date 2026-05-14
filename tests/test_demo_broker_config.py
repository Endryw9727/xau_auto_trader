from pathlib import Path

import pytest
import yaml

from src.broker.demo_broker_readonly import load_demo_broker_config


def test_demo_broker_config_is_readonly_safe():
    config = load_demo_broker_config(Path("config/demo_broker.yaml"))

    assert config.demo_only is True
    assert config.allow_live is False
    assert config.execution_enabled is False
    assert config.broker_name == "axi_demo"
    assert config.symbol == "XAUUSD"


def test_demo_broker_config_rejects_live_or_execution_enabled(tmp_path):
    path = tmp_path / "demo_broker.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "demo_only": True,
                "allow_live": True,
                "execution_enabled": False,
                "broker_name": "axi_demo",
                "platform": "mt5",
                "symbol": "XAUUSD",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PermissionError, match="allow_live"):
        load_demo_broker_config(path)

    path.write_text(
        yaml.safe_dump(
            {
                "demo_only": True,
                "allow_live": False,
                "execution_enabled": True,
                "broker_name": "axi_demo",
                "platform": "mt5",
                "symbol": "XAUUSD",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PermissionError, match="execution_enabled"):
        load_demo_broker_config(path)
