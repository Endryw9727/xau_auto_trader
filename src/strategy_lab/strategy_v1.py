"""
Strategy Lab v1: existing strategy wrapper.

This module intentionally delegates to the current production research
signal generator so the lab has a stable baseline.
"""

from __future__ import annotations

import pandas as pd

from src.strategy.rules import StrategyConfig
from src.strategy.signals import TradingSignal, generate_signal as generate_existing_signal


STRATEGY_NAME = "existing_strategy"


def generate_signal(df: pd.DataFrame, config: StrategyConfig | None = None) -> TradingSignal:
    """Generate the baseline signal using the existing strategy."""
    return generate_existing_signal(df, config)
