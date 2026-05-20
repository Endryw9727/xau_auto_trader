import pandas as pd

from src.control_room.audit_logger import write_control_room_outputs
from src.control_room.orchestrator import load_control_room_config
from src.control_room.shadow_monitor import SHADOW_COLUMNS


def test_control_room_audit_outputs_have_expected_columns(tmp_path):
    config = load_control_room_config()
    shadow = pd.DataFrame(
        [
            {
                "variant": "proxy_hardened_no_worst_hours_high_margin",
                "potential_signals": 1,
                "NO_TRADE": 1,
                "PAPER_BUY": 0,
                "PAPER_SELL": 0,
                "PAUSE": 0,
                "top_rejection_reasons": "test",
                "near_miss": "none",
            }
        ],
        columns=SHADOW_COLUMNS,
    )
    snapshots = {
        "market": {"status": "OK", "reason": "fresh"},
        "account": {"status": "WARNING", "reason": "mt5 unavailable"},
        "risk": {"status": "OK", "reason": "safe"},
        "signals": {"status": "OK", "reason": "loaded"},
        "shadow": {"status": "OK", "reason": "generated", "snapshot": shadow},
        "telegram": {"status": "OK", "reason": "disabled"},
    }

    paths = write_control_room_outputs(config, snapshots, status="WARNING", reason="test warning", output_dir=tmp_path)

    status = pd.read_csv(paths["status"])
    events = pd.read_csv(paths["events"])
    warnings = pd.read_csv(paths["warnings"])
    shadow_out = pd.read_csv(paths["shadow"])

    assert {"timestamp", "symbol", "status", "allow_real_live"}.issubset(status.columns)
    assert {"component", "status", "reason"}.issubset(events.columns)
    assert {"component", "status", "reason"}.issubset(warnings.columns)
    assert list(shadow_out.columns) == SHADOW_COLUMNS
