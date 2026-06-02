"""Tests for macro layer."""
import pandas as pd
import pytest
from src.macro.macro_config import MacroConfig
from src.macro.macro_engine import MacroEngine, MacroAnalysisResult
from src.macro.macro_snapshot import MacroSnapshot


def _mock_macro_fetchers(monkeypatch):
    df = pd.DataFrame({"Close": [100, 101, 102, 103, 104]})
    monkeypatch.setattr("src.macro.macro_engine.fetch_dxy", lambda: df)
    monkeypatch.setattr("src.macro.macro_engine.fetch_us10y", lambda: df)
    monkeypatch.setattr("src.macro.macro_engine.fetch_vix", lambda: df)
    monkeypatch.setattr("src.macro.macro_engine.fetch_spx", lambda: df)


def test_macro_config_defaults():
    config = MacroConfig()
    assert config.enabled is True
    assert config.dxy_weight == 0.35
    assert config.correlation_window == 50


def test_macro_snapshot_creation():
    snapshot = MacroSnapshot(
        dxy_value=105.5,
        dxy_trend="BULLISH",
        us10y_value=4.5,
        us10y_trend="BEARISH",
        vix_value=18.0,
        vix_level="normal",
    )
    assert snapshot.dxy_value == 105.5
    assert snapshot.vix_level == "normal"


def test_macro_snapshot_invalid_trend():
    with pytest.raises(ValueError, match="Invalid dxy_trend"):
        MacroSnapshot(dxy_trend="INVALID")


def test_macro_engine_analyze_offline(monkeypatch):
    """Test macro engine using mocked market data, never the network."""
    _mock_macro_fetchers(monkeypatch)
    engine = MacroEngine(MacroConfig(enabled=True))
    result = engine.analyze()
    assert isinstance(result, MacroAnalysisResult)
    assert result.snapshot is not None


def test_should_block_side_bullish_macro():
    config = MacroConfig(block_trade_against_macro=True, macro_score_threshold=0.30)
    engine = MacroEngine(config)

    result = MacroAnalysisResult(
        score=0.5,
        score_label="BULLISH",
        snapshot=MacroSnapshot(),
        dxy_correlation=None,
        confidence=0.8,
        block_trade=False,
        block_reason=None,
        explanation="test",
    )

    blocked, reason = engine.should_block_side(result, "SELL")
    assert blocked is True
    assert "macro" in reason.lower()
    assert "bullish" in reason.lower()


def test_should_not_block_neutral():
    config = MacroConfig(block_trade_against_macro=True, macro_score_threshold=0.30)
    engine = MacroEngine(config)

    result = MacroAnalysisResult(
        score=0.1,
        score_label="NEUTRAL",
        snapshot=MacroSnapshot(),
        dxy_correlation=None,
        confidence=0.5,
        block_trade=False,
        block_reason=None,
        explanation="test",
    )

    blocked, _ = engine.should_block_side(result, "BUY")
    assert blocked is False
