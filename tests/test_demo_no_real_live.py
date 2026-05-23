from pathlib import Path

import yaml

from src.execution.mt5_demo_executor import load_demo_execution_config


def test_demo_execution_never_enables_real_live(tmp_path):
    base_path = tmp_path / "demo_execution.yaml"
    raw = yaml.safe_load(Path("config/demo_execution.yaml").read_text(encoding="utf-8"))
    base_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    config = load_demo_execution_config(base_path)

    assert config.allow_real_live is False
    assert config.demo_only is True
    assert config.execution_enabled is False
    assert config.allow_demo_execution is False


def test_demo_execution_source_does_not_import_live_broker_or_use_forbidden_names():
    source = Path("src/execution/mt5_demo_executor.py").read_text(encoding="utf-8")

    assert "live_broker" not in source
    assert "api_key" not in source.lower()
    assert "place_order" not in source
    assert "execute_order" not in source
    assert "send_order" not in source
    assert "OrderSend" not in source
    assert "CTrade" not in source
