from scripts import paper_preflight_check as script
from src.market_data.mt5_readonly_data_updater import load_market_data_config


def test_preflight_auto_update_is_disabled_by_default():
    config = load_market_data_config("config/market_data.yaml")

    assert config.auto_update_data is False


def test_preflight_skips_auto_update_when_disabled(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("auto update should not run when disabled")

    monkeypatch.setattr(script, "update_market_data_from_mt5_readonly", fail_if_called)

    check = script.check_market_data_auto_update(script.DEFAULT_MARKET_DATA_CONFIG_PATH)

    assert check["passed"] is True
    assert check["status"] == "SKIPPED"
    assert "auto_update_data=false" in check["detail"]
