from pathlib import Path

import pytest
import yaml

from src.execution.mt5_demo_executor import load_demo_execution_config


def write_base_config(tmp_path, overrides=None):
    raw = yaml.safe_load(Path("config/demo_execution.yaml").read_text(encoding="utf-8"))
    if overrides:
        raw.update(overrides)
    path = tmp_path / "demo_execution.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def write_local_override(base_path, overrides):
    path = base_path.with_name(f"{base_path.stem}.local{base_path.suffix}")
    path.write_text(yaml.safe_dump(overrides), encoding="utf-8")
    return path


def test_demo_execution_loads_local_override(tmp_path):
    base_path = write_base_config(tmp_path)
    write_local_override(base_path, {"broker_name": "fortune_prime_demo"})

    config = load_demo_execution_config(base_path)

    assert config.broker_name == "fortune_prime_demo"


def test_demo_execution_local_override_keeps_allow_real_live_false(tmp_path):
    base_path = write_base_config(tmp_path)
    write_local_override(base_path, {"allow_real_live": False})

    config = load_demo_execution_config(base_path)

    assert config.allow_real_live is False


def test_demo_execution_local_override_can_enable_demo_execution(tmp_path):
    base_path = write_base_config(tmp_path)
    write_local_override(
        base_path,
        {
            "demo_only": True,
            "allow_real_live": False,
            "allow_demo_execution": True,
            "execution_enabled": True,
        },
    )

    config = load_demo_execution_config(base_path)

    assert config.allow_demo_execution is True
    assert config.execution_enabled is True
    assert config.demo_only is True
    assert config.allow_real_live is False


def test_demo_execution_local_override_can_set_symbol_xauusd_p(tmp_path):
    base_path = write_base_config(tmp_path, {"symbol": "XAUUSD"})
    write_local_override(base_path, {"symbol": "XAUUSD-P"})

    config = load_demo_execution_config(base_path)

    assert config.symbol == "XAUUSD-P"


def test_demo_execution_local_override_can_set_broker_name_fortune_prime_demo(tmp_path):
    base_path = write_base_config(tmp_path)
    write_local_override(base_path, {"broker_name": "fortune_prime_demo"})

    config = load_demo_execution_config(base_path)

    assert config.broker_name == "fortune_prime_demo"


def test_demo_execution_local_override_rejects_real_live(tmp_path):
    base_path = write_base_config(tmp_path)
    write_local_override(
        base_path,
        {
            "demo_only": True,
            "allow_real_live": True,
            "allow_demo_execution": True,
            "execution_enabled": True,
        },
    )

    with pytest.raises(PermissionError, match="allow_real_live"):
        load_demo_execution_config(base_path)
