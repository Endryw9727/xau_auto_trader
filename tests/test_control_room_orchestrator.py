import pandas as pd

from src.control_room.orchestrator import run_control_room_once


def test_control_room_orchestrator_runs_and_writes_outputs(tmp_path):
    result = run_control_room_once(output_dir=tmp_path)

    assert result.status in {"OK", "WARNING", "STOP"}
    assert "market" in result.snapshots
    assert "account" in result.snapshots
    assert "risk" in result.snapshots
    assert "signals" in result.snapshots
    assert "shadow" in result.snapshots
    assert result.output_paths["status"].exists()
    assert result.output_paths["events"].exists()
    assert result.output_paths["warnings"].exists()
    assert result.output_paths["shadow"].exists()

    status = pd.read_csv(result.output_paths["status"])
    assert "allow_real_live" in status.columns
    assert str(status.iloc[-1]["allow_real_live"]).lower() in {"false", "0"}
