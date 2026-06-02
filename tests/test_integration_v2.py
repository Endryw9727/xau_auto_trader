"""Integration tests for V2 layers."""
import pandas as pd
import pytest

from src.settings import load_settings
from src.macro.macro_engine import MacroEngine
from src.news.news_filter import NewsFilter
from src.strategy.smart_money.smart_money_analyzer import analyze_smart_money


def _mock_macro_fetchers(monkeypatch):
    df = pd.DataFrame({"Close": [100, 101, 102, 103, 104]})
    monkeypatch.setattr("src.macro.macro_engine.fetch_dxy", lambda: df)
    monkeypatch.setattr("src.macro.macro_engine.fetch_us10y", lambda: df)
    monkeypatch.setattr("src.macro.macro_engine.fetch_vix", lambda: df)
    monkeypatch.setattr("src.macro.macro_engine.fetch_spx", lambda: df)


def test_settings_loads_v2_config():
    settings = load_settings()
    assert hasattr(settings, "macro")
    assert hasattr(settings, "news")
    assert hasattr(settings, "ai_reasoning")
    assert hasattr(settings, "smart_money")
    assert settings.macro.enabled is True
    assert settings.news.enabled is True
    assert settings.ai_reasoning.enabled is True
    assert settings.smart_money.enabled is True


def test_macro_engine_offline(monkeypatch):
    _mock_macro_fetchers(monkeypatch)
    engine = MacroEngine()
    result = engine.analyze()
    assert result is not None
    assert -1.0 <= result.score <= 1.0


def test_news_filter_basic():
    filter = NewsFilter()
    result = filter.check()
    assert result.allowed in {True, False}
    assert result.risk_level in {"HIGH", "MEDIUM", "LOW"}


def test_smart_money_on_flat_data():
    df = pd.DataFrame({
        "Open": [2300]*50, "High": [2310]*50, "Low": [2290]*50,
        "Close": [2305]*50, "Volume": [1000]*50,
    })
    analysis = analyze_smart_money(df)
    assert analysis.bias == "NEUTRAL"


def test_full_pipeline_mock(monkeypatch):
    """Test that all V2 components can be instantiated together."""
    _mock_macro_fetchers(monkeypatch)
    settings = load_settings()

    # Macro
    macro = MacroEngine()
    macro_result = macro.analyze()

    # News
    news = NewsFilter()
    news_result = news.check()

    # Smart Money
    df = pd.DataFrame({
        "Open": [2300]*100, "High": [2310]*100, "Low": [2290]*100,
        "Close": [2305]*100, "Volume": [1000]*100,
    })
    sm = analyze_smart_money(df)

    assert macro_result is not None
    assert news_result is not None
    assert sm is not None
