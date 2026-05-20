from types import SimpleNamespace

from scripts import check_mt5_demo_execution_readiness as readiness_script
from src.execution.mt5_demo_executor import check_demo_execution_readiness, load_demo_execution_config


class FakeReadyMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 2

    def __init__(self, *, trade_mode=0, spread=10, visible=True, trade_allowed=True):
        self.trade_mode = trade_mode
        self.spread = spread
        self.visible = visible
        self.trade_allowed = trade_allowed
        self.shutdown_called = False

    def initialize(self):
        return True

    def shutdown(self):
        self.shutdown_called = True

    def account_info(self):
        return SimpleNamespace(
            login=123,
            trade_mode=self.trade_mode,
            trade_allowed=self.trade_allowed,
            server="Axi Demo",
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
            name=symbol,
            visible=self.visible,
            volume_min=0.01,
            volume_step=0.01,
            volume_max=100.0,
            trade_stops_level=50,
            filling_mode=1,
            spread=self.spread,
            point=0.01,
        )

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=2400.0, ask=2400.10)

    def last_error(self):
        return "fake"


def test_readiness_passes_with_demo_account():
    readiness = check_demo_execution_readiness(mt5_module=FakeReadyMT5())

    assert readiness.status == "OK"
    assert readiness.mt5_initialized is True
    assert readiness.account_connected is True
    assert readiness.account_demo is True
    assert readiness.trade_allowed is True
    assert readiness.symbol_found is True
    assert readiness.symbol_visible is True
    assert readiness.volume_min == 0.01
    assert readiness.volume_step == 0.01


def test_readiness_rejects_real_account():
    readiness = check_demo_execution_readiness(mt5_module=FakeReadyMT5(trade_mode=2))

    assert readiness.status == "ERROR"
    assert readiness.account_demo is False
    assert "not demo" in readiness.reason


def test_readiness_script_fails_safely_without_mt5(monkeypatch, capsys):
    monkeypatch.setattr("src.execution.mt5_demo_executor.import_mt5_module", lambda: None)

    readiness_script.main()
    output = capsys.readouterr().out

    assert "Demo Execution Readiness" in output
    assert "allow_real_live: False" in output
    assert "Status: MT5_NOT_AVAILABLE" in output


def test_demo_execution_config_defaults_are_safe():
    config = load_demo_execution_config()

    assert config.demo_only is True
    assert config.allow_demo_execution is False
    assert config.allow_real_live is False
    assert config.execution_enabled is False
    assert config.symbol == "XAUUSD-P"
