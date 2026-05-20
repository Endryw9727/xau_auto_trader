from pathlib import Path

from src.control_room.orchestrator import load_control_room_config
from src.paper.paper_candidate import PAPER_MAIN_STRATEGY


def test_control_room_has_no_execution_code_or_live_enablement():
    sources = "\n".join(path.read_text(encoding="utf-8") for path in Path("src/control_room").glob("*.py"))

    assert "order_send" not in sources
    assert "place_order" not in sources
    assert "execute_order" not in sources
    assert "send_order" not in sources
    assert "CTrade" not in sources
    assert "allow_real_live=True" not in sources


def test_control_room_does_not_change_paper_main():
    config = load_control_room_config()

    assert config.allow_real_live is False
    assert PAPER_MAIN_STRATEGY == "proxy_hardened_no_worst_hours_high_margin"
