from pathlib import Path

from src.broker.demo_broker_readonly import load_demo_broker_config
from src.market_data.mt5_readonly_data_updater import update_market_data_from_mt5_readonly
from tests.test_mt5_readonly_data_updater import FakeMT5, write_demo_config, write_market_config


def test_data_updater_never_calls_execution_method(tmp_path):
    market_config = tmp_path / "market_data.yaml"
    demo_config = tmp_path / "demo_broker.yaml"
    write_market_config(market_config, timeframes=("M15",))
    write_demo_config(demo_config)
    fake_mt5 = FakeMT5([])

    update_market_data_from_mt5_readonly(
        market_config_path=market_config,
        demo_config_path=demo_config,
        timeframe_dir=tmp_path / "timeframes",
        m15_csv_path=tmp_path / "xauusd.csv",
        mt5_module=fake_mt5,
    )

    assert fake_mt5.execution_called is False


def test_data_updater_source_has_no_execution_entrypoints():
    source = Path("src/market_data/mt5_readonly_data_updater.py").read_text(encoding="utf-8")

    assert "place_order" not in source
    assert "order_send" not in source
    assert "live_broker" not in source
    assert ".env" not in source


def test_demo_and_execution_flags_remain_disabled():
    config = load_demo_broker_config("config/demo_broker.yaml")

    assert config.demo_only is True
    assert config.allow_live is False
    assert config.execution_enabled is False
