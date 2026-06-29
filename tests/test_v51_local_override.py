from pathlib import Path

import pytest
import yaml

from src.strategy_lab import strategy_v51_demo_intraday as strategy
from src.strategy_lab.strategy_v51_demo_intraday import load_v51_config


def write_base(tmp_path, **overrides):
    raw = yaml.safe_load(Path("config/strategy_v51.yaml").read_text(encoding="utf-8"))
    raw.update(overrides)
    path = tmp_path / "strategy_v51.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def write_local(base_path: Path, overrides: dict) -> Path:
    path = base_path.with_name(f"{base_path.stem}.local{base_path.suffix}")
    path.write_text(yaml.safe_dump(overrides), encoding="utf-8")
    return path


def test_loads_without_local_override(tmp_path):
    base_path = write_base(tmp_path)
    config = load_v51_config(base_path)
    # Committed defaults stay disarmed.
    assert config.allow_demo_execution is False
    assert config.execution_enabled is False
    assert config.allow_real_live is False


def test_local_override_arms_demo_execution(tmp_path):
    base_path = write_base(tmp_path)
    write_local(base_path, {"allow_demo_execution": True, "execution_enabled": True})

    config = load_v51_config(base_path)

    assert config.allow_demo_execution is True
    assert config.execution_enabled is True
    assert config.allow_real_live is False  # never armed
    assert config.demo_only is True


def test_local_override_can_enable_guardrails(tmp_path):
    base_path = write_base(tmp_path)
    write_local(base_path, {"daily_loss_lock_enabled": True, "max_daily_loss_currency": 25.0})

    config = load_v51_config(base_path)

    assert config.daily_loss_lock_enabled is True
    assert config.max_daily_loss_currency == 25.0


def test_local_override_cannot_enable_real_live(tmp_path):
    base_path = write_base(tmp_path)
    write_local(base_path, {"allow_real_live": True})

    with pytest.raises(PermissionError):
        load_v51_config(base_path)


def test_base_config_cannot_enable_real_live(tmp_path):
    base_path = write_base(tmp_path, allow_real_live=True)

    with pytest.raises(PermissionError):
        load_v51_config(base_path)


def test_default_local_path_is_gitignored_sibling():
    assert strategy._local_v51_config_path(strategy.DEFAULT_V51_CONFIG_PATH) == strategy.DEFAULT_V51_LOCAL_CONFIG_PATH
    assert strategy.DEFAULT_V51_LOCAL_CONFIG_PATH.name == "strategy_v51.local.yaml"


def test_local_override_is_gitignored():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    assert "config/strategy_v51.local.yaml" in gitignore


def test_example_template_exists_and_is_safe():
    example = Path("config/strategy_v51.local.yaml.example")
    assert example.exists()
    raw = yaml.safe_load(example.read_text(encoding="utf-8"))
    assert raw["allow_real_live"] is False
