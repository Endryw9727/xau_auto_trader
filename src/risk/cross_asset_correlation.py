"""
Cross-asset correlation analyzer.

Calculates rolling correlations between assets and provides
a real-time correlation heatmap for portfolio risk management.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

@dataclass(frozen=True)
class CorrelationAlert:
    """Alert for correlation regime change."""

    asset_pair: tuple[str, str]
    old_correlation: float
    new_correlation: float
    regime_change: str  # "increasing", "decreasing", "sign_flip"
    severity: str  # "info", "warning", "critical"


class CrossAssetCorrelation:
    """Manages cross-asset correlation analysis."""

    def __init__(self, lookback_window: int = 50, alert_threshold: float = 0.15):
        self.lookback_window = lookback_window
        self.alert_threshold = alert_threshold
        self._price_history: dict[str, pd.Series] = {}
        self._last_correlation: pd.DataFrame | None = None

    def add_price_data(self, symbol: str, prices: pd.Series) -> None:
        """Add or update price series for a symbol."""
        self._price_history[symbol] = prices

    def calculate_correlation_matrix(self) -> pd.DataFrame:
        """Calculate current correlation matrix from returns."""
        if len(self._price_history) < 2:
            return pd.DataFrame()

        price_data = {}
        for symbol, prices in self._price_history.items():
            clean_prices = prices.dropna()
            if len(clean_prices) >= 2:
                window = min(self.lookback_window, len(clean_prices))
                price_data[symbol] = clean_prices.iloc[-window:].reset_index(drop=True)

        if len(price_data) < 2:
            return pd.DataFrame()

        prices_df = pd.DataFrame(price_data).dropna()
        if len(prices_df) < 2:
            return pd.DataFrame()

        corr = prices_df.corr().fillna(0.0)
        for symbol in corr.columns:
            corr.loc[symbol, symbol] = 1.0
        self._last_correlation = corr
        return corr

    def get_correlation(self, symbol1: str, symbol2: str) -> float | None:
        """Get correlation between two specific assets."""
        corr = self.calculate_correlation_matrix()
        if corr.empty:
            return None
        if symbol1 not in corr.columns or symbol2 not in corr.columns:
            return None
        return float(corr.loc[symbol1, symbol2])

    def check_regime_changes(self) -> list[CorrelationAlert]:
        """Check for significant correlation regime changes."""
        current = self.calculate_correlation_matrix()
        if current.empty or self._last_correlation is None:
            return []

        alerts: list[CorrelationAlert] = []
        symbols = current.columns

        for i, s1 in enumerate(symbols):
            for s2 in symbols[i+1:]:
                old = self._last_correlation.loc[s1, s2]
                new = current.loc[s1, s2]
                change = abs(new - old)

                if change > self.alert_threshold:
                    if old * new < 0:
                        regime = "sign_flip"
                        severity = "critical"
                    elif abs(new) > abs(old):
                        regime = "increasing"
                        severity = "warning" if abs(new) > 0.8 else "info"
                    else:
                        regime = "decreasing"
                        severity = "info"

                    alerts.append(CorrelationAlert(
                        asset_pair=(s1, s2),
                        old_correlation=round(old, 3),
                        new_correlation=round(new, 3),
                        regime_change=regime,
                        severity=severity,
                    ))

        return alerts

    def get_diversification_score(self) -> float:
        """
        Calculate portfolio diversification score.

        1.0 = perfectly diversified (all correlations = 0)
        0.0 = no diversification (all correlations = 1)
        """
        corr = self.calculate_correlation_matrix()
        if corr.empty:
            return 0.0

        # Average absolute correlation (excluding diagonal)
        abs_corr = corr.abs()
        n = len(abs_corr)
        if n <= 1:
            return 1.0

        total = abs_corr.sum().sum() - n  # Subtract diagonal (all 1s)
        pairs = n * (n - 1)
        avg_corr = total / pairs if pairs > 0 else 0.0

        # Score: 1 - avg_corr
        score = 1.0 - avg_corr
        return round(max(0.0, min(1.0, float(score))), 3)

    def get_hedge_candidates(self, target_symbol: str, min_correlation: float = -0.5) -> list[dict[str, Any]]:
        """Find assets negatively correlated with target for hedging."""
        corr = self.calculate_correlation_matrix()
        if corr.empty or target_symbol not in corr.columns:
            return []

        candidates = []
        for symbol in corr.columns:
            if symbol == target_symbol:
                continue
            c = corr.loc[target_symbol, symbol]
            if c <= min_correlation:
                candidates.append({
                    "symbol": symbol,
                    "correlation": round(c, 3),
                    "hedge_strength": round(abs(c), 3),
                })

        return sorted(candidates, key=lambda x: x["correlation"])
