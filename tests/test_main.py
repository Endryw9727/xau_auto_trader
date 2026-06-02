"""Tests for main module."""
from src.main import build_strategy_config, build_backtest_config
from src.settings import load_settings

def test_build_configs():
    settings = load_settings()
    strategy_config = build_strategy_config(settings)
    backtest_config = build_backtest_config(settings)
    assert strategy_config.symbol == "XAUUSD"
    assert backtest_config.initial_balance > 0
