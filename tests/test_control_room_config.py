import pytest
import yaml

from src.control_room.orchestrator import load_control_room_config
from src.paper.paper_candidate import PAPER_MAIN_STRATEGY


def test_control_room_config_defaults_are_safe():
    config = load_control_room_config("config/control_room.yaml")

    assert config.enabled is True
    assert config.symbol == "XAUUSD-P"
    assert config.mode == "demo_monitor"
    assert config.allow_real_live is False
    assert config.allow_demo_execution is True
    assert config.telegram_enabled is False
    assert "proxy_hardened_no_worst_hours_high_margin" in config.shadow_variants
    assert PAPER_MAIN_STRATEGY == "proxy_hardened_no_worst_hours_high_margin"


def test_control_room_config_rejects_real_live(tmp_path):
    raw = yaml.safe_load(open("config/control_room.yaml", encoding="utf-8"))
    raw["allow_real_live"] = True
    path = tmp_path / "control_room.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(PermissionError, match="allow_real_live"):
        load_control_room_config(path)
