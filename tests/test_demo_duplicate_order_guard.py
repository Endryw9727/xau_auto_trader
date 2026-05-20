from types import SimpleNamespace

import pandas as pd

from src.execution.mt5_demo_executor import MT5DemoExecutor
from tests.test_mt5_demo_executor_safety import FakeDemoMT5, make_request, write_enabled_config


def test_duplicate_signal_in_local_order_log_blocks_request(tmp_path):
    config = write_enabled_config(tmp_path / "demo_execution.yaml")
    pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
                "signal_id": "dup-signal",
                "status": "SENT",
            }
        ]
    ).to_csv(tmp_path / "demo_orders.csv", index=False)
    fake = FakeDemoMT5()
    executor = MT5DemoExecutor(config, mt5_module=fake, output_dir=tmp_path)

    result = executor.submit_demo_market_order(make_request("dup-signal"), dry_run=False)

    assert result.accepted is False
    assert "duplicate" in result.reason
    assert fake.order_send_called is False


def test_duplicate_signal_in_open_positions_blocks_request(tmp_path):
    config = write_enabled_config(tmp_path / "demo_execution.yaml")
    position = SimpleNamespace(magic=config.magic_number, comment="demo:open-signal", type=0)
    fake = FakeDemoMT5(positions=[position])
    executor = MT5DemoExecutor(config, mt5_module=fake, output_dir=tmp_path)

    result = executor.submit_demo_market_order(make_request("open-signal"), dry_run=False)

    assert result.accepted is False
    assert "max_open_positions" in result.reason or "duplicate" in result.reason
    assert fake.order_send_called is False
