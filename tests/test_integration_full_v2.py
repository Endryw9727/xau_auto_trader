"""Full integration test for V2 pipeline."""
import pandas as pd

from src.settings import load_settings
from src.macro.macro_engine import MacroEngine
from src.news.news_filter import NewsFilter
from src.strategy.signals_v2 import generate_signals_v2
from src.strategy.rules import StrategyConfig
from src.strategy.smart_money.smart_money_analyzer import analyze_smart_money
from src.ai_reasoning.context_builder import build_context
from src.ai_reasoning.score_composer import ScoreWeights, compose_score
from src.ai_reasoning.warning_system import generate_warnings, should_block


def _mock_macro_fetchers(monkeypatch):
    df = pd.DataFrame({"Close": [100, 101, 102, 103, 104]})
    monkeypatch.setattr("src.macro.macro_engine.fetch_dxy", lambda: df)
    monkeypatch.setattr("src.macro.macro_engine.fetch_us10y", lambda: df)
    monkeypatch.setattr("src.macro.macro_engine.fetch_vix", lambda: df)
    monkeypatch.setattr("src.macro.macro_engine.fetch_spx", lambda: df)


def test_full_pipeline(monkeypatch):
    """Test that all V2 components work together."""
    _mock_macro_fetchers(monkeypatch)
    settings = load_settings()

    # Create synthetic data
    prices = list(range(1, 301))
    df = pd.DataFrame({
        "Open": [p - 0.5 for p in prices],
        "High": [p + 1 for p in prices],
        "Low": [p - 1 for p in prices],
        "Close": prices,
        "Volume": [1000]*300,
    })

    # Smart Money
    sm = analyze_smart_money(df, lookback=20)
    assert sm.bias in {"BULLISH", "BEARISH", "NEUTRAL"}

    # Macro (offline fallback)
    macro = MacroEngine()
    macro_result = macro.analyze(df)
    assert -1.0 <= macro_result.score <= 1.0

    # News
    news = NewsFilter()
    news_result = news.check()
    assert news_result.allowed in {True, False}

    # Signals V2
    config = StrategyConfig()
    signals = generate_signals_v2(df, config, use_smc=True)
    assert "smc_score" in signals.columns

    last = signals.iloc[-1]
    if str(last["signal"]) != "NO_TRADE":
        # AI Reasoning
        context = build_context(
            df=df, signal_row=last,
            macro_result=macro_result,
            news_result=news_result,
            account_balance=1000,
            open_trades=0,
            daily_loss=0.0,
            consecutive_losses=0,
        )
        weights = ScoreWeights()
        composite = compose_score(context, weights)
        assert 0 <= composite.score <= 1
        assert composite.recommendation in {"STRONG_BUY", "BUY", "WEAK_BUY", "NO_TRADE", "WEAK_SELL", "SELL", "STRONG_SELL"}

        warnings = generate_warnings(context, composite)
        blocked, reason = should_block(warnings)
        assert isinstance(blocked, bool)
