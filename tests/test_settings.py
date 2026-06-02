"""Tests for settings loader."""
from src.settings import load_settings

def test_load_settings(monkeypatch):
    monkeypatch.delenv("LIVE_MODE", raising=False)
    settings = load_settings()
    assert settings.trading.symbol == "XAUUSD"
    assert settings.trading.live_mode is False
