"""
Strategy Lab v6: relaxed Off Session + Asia feature-filtered candidate.

This research candidate promotes the best balanced relaxed sweep variant into
the Strategy Lab without changing the protected execution layer.
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from src.strategy.rules import StrategyConfig
from src.strategy.signals import TradingSignal
from src.strategy_lab.strategy_v5 import (
    FeatureFilterConfig,
    REQUIRED_HISTORY_CANDLES,
    generate_signal_with_filters,
)


STRATEGY_NAME = "mtf_relaxed_offasia_strategy"
REQUIRED_RISK_PER_TRADE = 0.005
REQUIRED_MIN_RISK_REWARD = 2.0
REQUIRED_ALLOWED_SESSIONS = ["Off Session", "Asia"]
RELAXED_MIN_ADX = 0.0
RELAXED_FILTER_CONFIG = FeatureFilterConfig(
    allowed_trend_regimes=None,
    allowed_candle_regimes=None,
    allowed_adx_buckets=None,
    min_adx=None,
)


def generate_signal(df: pd.DataFrame, config: StrategyConfig | None = None) -> TradingSignal:
    """Generate the relaxed Off Session + Asia candidate signal."""
    if config is None:
        config = StrategyConfig()

    relaxed_config = replace(
        config,
        min_adx=RELAXED_MIN_ADX,
        min_risk_reward=REQUIRED_MIN_RISK_REWARD,
    )

    return generate_signal_with_filters(
        df,
        relaxed_config,
        RELAXED_FILTER_CONFIG,
    )


generate_signal.required_history_candles = REQUIRED_HISTORY_CANDLES
