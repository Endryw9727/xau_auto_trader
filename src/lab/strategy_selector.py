"""
Strategy selector based on market regime.

Selects the best strategy parameters for current market conditions.
Uses regime detection + historical performance per regime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.ml.regime_detector import RegimeAnalysis, detect_regime

@dataclass(frozen=True)
class StrategyProfile:
    """Strategy parameters optimized for a specific regime."""

    name: str
    regime: str
    atr_multiplier_sl: float
    atr_multiplier_tp: float
    rsi_buy_max: float
    rsi_sell_min: float
    min_adx: float
    min_risk_reward: float
    use_smc: bool
    min_smc_score: float
    description: str

# Pre-defined strategy profiles per regime
DEFAULT_PROFILES: list[StrategyProfile] = [
    StrategyProfile(
        name="trend_follower_long",
        regime="TRENDING_UP",
        atr_multiplier_sl=1.5,
        atr_multiplier_tp=4.0,
        rsi_buy_max=65.0,
        rsi_sell_min=30.0,
        min_adx=25,
        min_risk_reward=2.5,
        use_smc=True,
        min_smc_score=0.2,
        description="Trend following in uptrend — wider TP, tighter RSI",
    ),
    StrategyProfile(
        name="trend_follower_short",
        regime="TRENDING_DOWN",
        atr_multiplier_sl=1.5,
        atr_multiplier_tp=4.0,
        rsi_buy_max=70.0,
        rsi_sell_min=35.0,
        min_adx=25,
        min_risk_reward=2.5,
        use_smc=True,
        min_smc_score=0.2,
        description="Trend following in downtrend — wider TP, tighter RSI",
    ),
    StrategyProfile(
        name="range_trader",
        regime="RANGING",
        atr_multiplier_sl=1.0,
        atr_multiplier_tp=2.0,
        rsi_buy_max=60.0,
        rsi_sell_min=40.0,
        min_adx=15,
        min_risk_reward=1.5,
        use_smc=True,
        min_smc_score=0.3,
        description="Mean reversion in range — tighter SL/TP, stricter SMC",
    ),
    StrategyProfile(
        name="volatility_guard",
        regime="VOLATILE",
        atr_multiplier_sl=2.0,
        atr_multiplier_tp=3.0,
        rsi_buy_max=75.0,
        rsi_sell_min=25.0,
        min_adx=20,
        min_risk_reward=2.0,
        use_smc=False,
        min_smc_score=0.0,
        description="High volatility — wider SL, no SMC requirement",
    ),
    StrategyProfile(
        name="low_vol_patience",
        regime="LOW_VOLATILITY",
        atr_multiplier_sl=1.5,
        atr_multiplier_tp=3.0,
        rsi_buy_max=70.0,
        rsi_sell_min=30.0,
        min_adx=18,
        min_risk_reward=2.0,
        use_smc=True,
        min_smc_score=0.4,
        description="Low volatility — stricter SMC, fewer trades",
    ),
]


class StrategySelector:
    """Selects optimal strategy based on market regime."""

    def __init__(self, profiles: list[StrategyProfile] | None = None):
        self.profiles = profiles or DEFAULT_PROFILES
        self._performance_log: list[dict] = []

    def select(self, df: pd.DataFrame) -> tuple[StrategyProfile, RegimeAnalysis]:
        """
        Select best strategy profile for current market conditions.

        Parameters:
        - df: OHLCV DataFrame

        Returns:
        - (StrategyProfile, RegimeAnalysis)
        """
        regime = detect_regime(df)

        # Find matching profile
        profile = next(
            (p for p in self.profiles if p.regime == regime.regime),
            self.profiles[0]  # Default to first profile
        )

        return profile, regime

    def log_performance(
        self,
        regime: str,
        profile_name: str,
        trades: int,
        win_rate: float,
        profit_factor: float,
    ) -> None:
        """Log performance for a regime/profile combination."""
        self._performance_log.append({
            "regime": regime,
            "profile": profile_name,
            "trades": trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
        })

    def get_best_profile_for_regime(self, regime: str) -> StrategyProfile | None:
        """Get the best performing profile for a given regime from history."""
        if not self._performance_log:
            return None

        regime_logs = [log for log in self._performance_log if log["regime"] == regime]
        if not regime_logs:
            return None

        # Sort by profit_factor descending
        best = max(regime_logs, key=lambda x: x["profit_factor"])
        return next((p for p in self.profiles if p.name == best["profile"]), None)

    def get_performance_summary(self) -> pd.DataFrame:
        """Get performance summary as DataFrame."""
        if not self._performance_log:
            return pd.DataFrame()
        return pd.DataFrame(self._performance_log)


def apply_profile_to_config(profile: StrategyProfile, settings: Any) -> Any:
    """
    Apply a strategy profile to settings.

    Returns updated settings with profile parameters.
    """
    # This is a simplified version — in practice you'd deep copy settings
    # and update the relevant fields
    return {
        "profile_name": profile.name,
        "description": profile.description,
        "atr_multiplier_sl": profile.atr_multiplier_sl,
        "atr_multiplier_tp": profile.atr_multiplier_tp,
        "rsi_buy_max": profile.rsi_buy_max,
        "rsi_sell_min": profile.rsi_sell_min,
        "min_adx": profile.min_adx,
        "min_risk_reward": profile.min_risk_reward,
        "use_smc": profile.use_smc,
        "min_smc_score": profile.min_smc_score,
    }
