from pathlib import Path

import src.execution as execution


def test_execution_layer_is_disabled_placeholder():
    assert execution.EXECUTION_LAYER_ENABLED is False
    assert execution.ALLOW_LIVE is False


def test_execution_layer_has_no_order_sending_code():
    execution_dir = Path("src/execution")
    sources = "\n".join(path.read_text(encoding="utf-8") for path in execution_dir.glob("*.py"))
    lowered = sources.lower()

    assert "live_broker" not in lowered
    assert "api_key" not in lowered
    assert "send_order" not in lowered
    assert "place_order" not in lowered
    assert "execute_order" not in lowered
