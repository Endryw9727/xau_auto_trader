"""Tests for multi-asset support."""
from src.market_data.asset_registry import (
    ASSET_REGISTRY, AssetConfig, get_asset_config, list_available_assets,
    get_asset_specific_strategy_config,
)


def test_asset_registry_has_xauusd():
    assert "XAUUSD" in ASSET_REGISTRY
    assert ASSET_REGISTRY["XAUUSD"].asset_class == "commodity"


def test_asset_registry_has_eurusd():
    assert "EURUSD" in ASSET_REGISTRY
    assert ASSET_REGISTRY["EURUSD"].asset_class == "forex"


def test_asset_registry_has_btcusd():
    assert "BTCUSD" in ASSET_REGISTRY
    assert ASSET_REGISTRY["BTCUSD"].asset_class == "crypto"


def test_get_asset_config_known():
    config = get_asset_config("XAUUSD")
    assert config.symbol == "XAUUSD"
    assert config.pip_decimal_places == 2


def test_get_asset_config_unknown():
    config = get_asset_config("UNKNOWN")
    assert config.symbol == "UNKNOWN"
    assert config.asset_class == "forex"


def test_list_available_assets():
    assets = list_available_assets()
    assert "XAUUSD" in assets
    assert "EURUSD" in assets
    assert "BTCUSD" in assets


def test_get_asset_specific_strategy_config():
    base = {"atr_multiplier_sl": 1.0, "rsi_buy_max": 60.0}
    config = get_asset_specific_strategy_config("XAUUSD", base)
    assert config["atr_multiplier_sl"] == 1.5  # XAUUSD override
    assert config["rsi_buy_max"] == 70.0  # XAUUSD override


def test_asset_session_relevance():
    config = get_asset_config("USDJPY")
    assert config.session_relevance["Asia"] == 1.0
    assert config.session_relevance["London"] == 0.8


def test_btcusd_24_7():
    config = get_asset_config("BTCUSD")
    assert config.trading_hours == "24/7"
    assert config.volatility_profile == "extreme"
