"""Tests for strategy selector."""
import pandas as pd

from src.lab.strategy_selector import StrategySelector, DEFAULT_PROFILES, apply_profile_to_config
from src.ml.regime_detector import detect_regime


def test_selector_defaults():
    selector = StrategySelector()
    assert len(selector.profiles) == 5


def test_selector_trending_up():
    prices = list(range(1, 101))
    df = pd.DataFrame({
        "Open": [p - 0.5 for p in prices],
        "High": [p + 1 for p in prices],
        "Low": [p - 1 for p in prices],
        "Close": prices,
        "Volume": [1000]*100,
    })
    selector = StrategySelector()
    profile, regime = selector.select(df)
    assert profile.regime == regime.regime
    assert profile.atr_multiplier_sl > 0


def test_apply_profile():
    profile = DEFAULT_PROFILES[0]
    config = apply_profile_to_config(profile, None)
    assert config["profile_name"] == profile.name
    assert config["atr_multiplier_sl"] == profile.atr_multiplier_sl


def test_performance_log():
    selector = StrategySelector()
    selector.log_performance("TRENDING_UP", "trend_follower_long", 10, 60.0, 1.5)
    summary = selector.get_performance_summary()
    assert len(summary) == 1
