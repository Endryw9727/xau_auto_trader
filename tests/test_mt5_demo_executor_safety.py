from types import SimpleNamespace

import pytest
import yaml

from src.execution.mt5_demo_executor import (
    DemoOrderRequest,
    MT5DemoExecutor,
    load_demo_execution_config,
)


class FakeDemoMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 2
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_PLACED = 10008
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1

    def __init__(self, *, demo=True, spread=10, positions=None, trade_allowed=True):
        self.demo = demo
        self.spread = spread
        self.positions = positions or []
        self.trade_allowed = trade_allowed
        self.order_send_called = False
        self.last_request = None

    def initialize(self):
        return True

    def shutdown(self):
        return None

    def account_info(self):
        return SimpleNamespace(
            trade_mode=self.ACCOUNT_TRADE_MODE_DEMO if self.demo else self.ACCOUNT_TRADE_MODE_REAL,
            trade_allowed=self.trade_allowed,
            server="Axi Demo" if self.demo else "Axi Real",
            balance=1000.0,
            equity=1000.0,
            margin=0.0,
            margin_free=1000.0,
            currency="EUR",
        )

    def terminal_info(self):
        return SimpleNamespace(trade_allowed=self.trade_allowed)

    def symbol_info(self, symbol):
        return SimpleNamespace(
            visible=True,
            volume_min=0.01,
            volume_step=0.01,
            volume_max=1.0,
            trade_stops_level=50,
            filling_mode=1,
            spread=self.spread,
            point=0.01,
        )

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=2400.0, ask=2400.10)

    def positions_get(self, symbol=None):
        return self.positions

    def order_send(self, request):
        self.order_send_called = True
        self.last_request = request
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=12345, deal=67890, comment="done")

    def last_error(self):
        return "fake"


def write_enabled_config(path):
    raw = yaml.safe_load(open("config/demo_execution.yaml", encoding="utf-8"))
    raw["allow_demo_execution"] = True
    raw["execution_enabled"] = True
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return load_demo_execution_config(path)


def make_request(signal_id="sig-1", volume=0.01, expected_price=2400.10):
    return DemoOrderRequest(
        signal_id=signal_id,
        side="BUY",
        volume=volume,
        stop_loss=2395.0,
        take_profit=2410.0,
        expected_price=expected_price,
    )


def test_default_config_blocks_actual_demo_execution(tmp_path):
    config = load_demo_execution_config()
    fake = FakeDemoMT5()
    executor = MT5DemoExecutor(config, mt5_module=fake, output_dir=tmp_path)

    result = executor.submit_demo_market_order(make_request(), dry_run=False, persist=False)

    assert result.accepted is False
    assert "allow_demo_execution=false" in result.reason
    assert fake.order_send_called is False


def test_dry_run_does_not_call_mt5_or_write_reports(tmp_path):
    config = load_demo_execution_config()
    fake = FakeDemoMT5()
    executor = MT5DemoExecutor(config, mt5_module=fake, output_dir=tmp_path)

    result = executor.submit_demo_market_order(make_request(), dry_run=True, persist=False)

    assert result.accepted is True
    assert result.status == "DRY_RUN"
    assert fake.order_send_called is False
    assert not (tmp_path / "demo_orders.csv").exists()


def test_missing_sl_or_tp_blocks_before_mt5(tmp_path):
    config = load_demo_execution_config()
    fake = FakeDemoMT5()
    executor = MT5DemoExecutor(config, mt5_module=fake, output_dir=tmp_path)
    request = DemoOrderRequest("sig-no-sl", "BUY", 0.01, None, 2410.0)

    result = executor.submit_demo_market_order(request, dry_run=False)

    assert result.accepted is False
    assert "stop loss" in result.reason
    assert fake.order_send_called is False


def test_enabled_demo_execution_sends_only_when_demo_and_all_gates_pass(tmp_path):
    config = write_enabled_config(tmp_path / "demo_execution.yaml")
    fake = FakeDemoMT5()
    executor = MT5DemoExecutor(config, mt5_module=fake, output_dir=tmp_path)

    result = executor.submit_demo_market_order(make_request(), dry_run=False, persist=True)

    assert result.accepted is True
    assert result.status == "SENT"
    assert fake.order_send_called is True
    assert fake.last_request["magic"] == config.magic_number
    assert fake.last_request["sl"] == 2395.0
    assert fake.last_request["tp"] == 2410.0
    assert (tmp_path / "demo_orders.csv").exists()


def test_non_demo_account_blocks_request(tmp_path):
    config = write_enabled_config(tmp_path / "demo_execution.yaml")
    fake = FakeDemoMT5(demo=False)
    executor = MT5DemoExecutor(config, mt5_module=fake, output_dir=tmp_path)

    result = executor.submit_demo_market_order(make_request(), dry_run=False)

    assert result.accepted is False
    assert "not demo" in result.reason
    assert fake.order_send_called is False


def test_spread_and_volume_gates_block_request(tmp_path):
    config = write_enabled_config(tmp_path / "demo_execution.yaml")
    high_spread = FakeDemoMT5(spread=999)
    executor = MT5DemoExecutor(config, mt5_module=high_spread, output_dir=tmp_path)

    spread_result = executor.submit_demo_market_order(make_request("sig-spread"), dry_run=False)
    volume_result = executor.submit_demo_market_order(make_request("sig-volume", volume=0.02), dry_run=False)

    assert spread_result.accepted is False
    assert "spread" in spread_result.reason
    assert volume_result.accepted is False
    assert "volume" in volume_result.reason
    assert high_spread.order_send_called is False


def test_config_rejects_allow_real_live(tmp_path):
    raw = yaml.safe_load(open("config/demo_execution.yaml", encoding="utf-8"))
    raw["allow_real_live"] = True
    path = tmp_path / "demo_execution.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(PermissionError, match="allow_real_live"):
        load_demo_execution_config(path)
