"""
Portfolio-level risk management.

Manages risk across multiple positions and assets:
- Portfolio heat (total risk exposure)
- Cross-asset correlation risk
- Sector concentration limits
- Maximum portfolio drawdown
- Correlation-adjusted position sizing
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.market_data.asset_registry import AssetConfig, get_asset_config

@dataclass(frozen=True)
class PortfolioPosition:
    """A position within the portfolio."""

    symbol: str
    side: str
    units: float
    entry_price: float
    current_price: float
    stop_loss: float
    risk_amount: float  # Dollar risk at entry
    unrealized_pnl: float
    asset_class: str

@dataclass(frozen=True)
class PortfolioRiskConfig:
    """Portfolio risk configuration."""

    max_portfolio_heat: float = 0.10  # Max 10% of equity at risk
    max_single_asset_heat: float = 0.05  # Max 5% per asset
    max_asset_class_heat: float = 0.08  # Max 8% per asset class
    max_correlated_exposure: float = 0.06  # Max for correlated assets
    max_open_positions: int = 5
    max_drawdown_pct: float = 0.15  # Hard stop at 15% portfolio DD
    correlation_threshold: float = 0.70  # Assets with |corr| > 0.7 are "correlated"

@dataclass(frozen=True)
class PortfolioRiskCheck:
    """Result of portfolio risk check."""

    allowed: bool
    reason: str
    current_heat: float
    heat_after_trade: float
    available_risk: float
    warnings: list[str]


class PortfolioRiskManager:
    """Manages risk at the portfolio level across all assets."""

    def __init__(self, config: PortfolioRiskConfig | None = None):
        self.config = config or PortfolioRiskConfig()
        self.positions: list[PortfolioPosition] = []
        self.equity: float = 0.0
        self._correlation_matrix: pd.DataFrame | None = None

    def update_equity(self, equity: float) -> None:
        """Update current portfolio equity."""
        self.equity = equity

    def set_correlation_matrix(self, matrix: pd.DataFrame) -> None:
        """Set cross-asset correlation matrix."""
        self._correlation_matrix = matrix

    def add_position(self, position: PortfolioPosition) -> None:
        """Add a position to the portfolio."""
        self.positions.append(position)

    def remove_position(self, symbol: str) -> None:
        """Remove a position by symbol."""
        self.positions = [p for p in self.positions if p.symbol != symbol]

    def check_new_trade(
        self,
        symbol: str,
        side: str,
        units: float,
        entry: float,
        stop_loss: float,
        risk_amount: float,
    ) -> PortfolioRiskCheck:
        """
        Check if a new trade can be added to the portfolio.

        Parameters:
        - symbol: proposed symbol
        - side: BUY or SELL
        - units: position size
        - entry: entry price
        - stop_loss: stop loss price
        - risk_amount: dollar risk

        Returns:
        - PortfolioRiskCheck with approval status
        """
        if self.equity <= 0:
            return PortfolioRiskCheck(
                allowed=False,
                reason="Portfolio equity is zero or negative",
                current_heat=0.0,
                heat_after_trade=0.0,
                available_risk=0.0,
                warnings=[],
            )

        warnings: list[str] = []

        # Current portfolio heat
        current_heat = self._calculate_portfolio_heat()
        heat_after = current_heat + (risk_amount / self.equity)

        # Check 1: Max portfolio heat
        if heat_after > self.config.max_portfolio_heat:
            return PortfolioRiskCheck(
                allowed=False,
                reason=f"Portfolio heat would exceed {self.config.max_portfolio_heat:.1%} "
                       f"({heat_after:.1%} > {self.config.max_portfolio_heat:.1%})",
                current_heat=current_heat,
                heat_after_trade=heat_after,
                available_risk=(self.config.max_portfolio_heat - current_heat) * self.equity,
                warnings=warnings,
            )

        # Check 2: Max single asset heat
        asset_heat = self._calculate_asset_heat(symbol) + (risk_amount / self.equity)
        if asset_heat > self.config.max_single_asset_heat:
            return PortfolioRiskCheck(
                allowed=False,
                reason=f"Single asset heat would exceed {self.config.max_single_asset_heat:.1%} "
                       f"({asset_heat:.1%} for {symbol})",
                current_heat=current_heat,
                heat_after_trade=heat_after,
                available_risk=(self.config.max_single_asset_heat - self._calculate_asset_heat(symbol)) * self.equity,
                warnings=warnings,
            )

        # Check 3: Max positions
        if len(self.positions) >= self.config.max_open_positions:
            return PortfolioRiskCheck(
                allowed=False,
                reason=f"Max open positions reached ({self.config.max_open_positions})",
                current_heat=current_heat,
                heat_after_trade=heat_after,
                available_risk=0.0,
                warnings=warnings,
            )

        # Check 4: Asset class concentration
        asset_config = get_asset_config(symbol)
        class_heat = self._calculate_asset_class_heat(asset_config.asset_class) + (risk_amount / self.equity)
        if class_heat > self.config.max_asset_class_heat:
            return PortfolioRiskCheck(
                allowed=False,
                reason=f"Asset class heat would exceed {self.config.max_asset_class_heat:.1%} "
                       f"({class_heat:.1%} for {asset_config.asset_class})",
                current_heat=current_heat,
                heat_after_trade=heat_after,
                available_risk=(self.config.max_asset_class_heat - self._calculate_asset_class_heat(asset_config.asset_class)) * self.equity,
                warnings=warnings,
            )

        # Check 5: Correlated exposure
        correlated_risk = self._calculate_correlated_exposure(symbol) + risk_amount
        if correlated_risk / self.equity > self.config.max_correlated_exposure:
            warnings.append(
                f"Correlated exposure high: {correlated_risk/self.equity:.1%} "
                f"(limit {self.config.max_correlated_exposure:.1%})"
            )

        # Check 6: Drawdown
        current_dd = self._calculate_drawdown()
        if current_dd > self.config.max_drawdown_pct:
            return PortfolioRiskCheck(
                allowed=False,
                reason=f"Portfolio drawdown exceeded limit: {current_dd:.1%} > {self.config.max_drawdown_pct:.1%}",
                current_heat=current_heat,
                heat_after_trade=heat_after,
                available_risk=0.0,
                warnings=warnings,
            )

        available_risk = (self.config.max_portfolio_heat - current_heat) * self.equity

        return PortfolioRiskCheck(
            allowed=True,
            reason="Portfolio risk check passed",
            current_heat=current_heat,
            heat_after_trade=heat_after,
            available_risk=available_risk,
            warnings=warnings,
        )

    def get_portfolio_summary(self) -> dict[str, Any]:
        """Get portfolio risk summary."""
        heat = self._calculate_portfolio_heat()
        dd = self._calculate_drawdown()

        asset_class_breakdown: dict[str, float] = {}
        for p in self.positions:
            ac = get_asset_config(p.symbol).asset_class
            asset_class_breakdown[ac] = asset_class_breakdown.get(ac, 0.0) + p.risk_amount

        return {
            "equity": self.equity,
            "total_positions": len(self.positions),
            "portfolio_heat": heat,
            "portfolio_heat_pct": f"{heat:.1%}",
            "drawdown": dd,
            "drawdown_pct": f"{dd:.1%}",
            "available_risk": (self.config.max_portfolio_heat - heat) * self.equity,
            "asset_class_breakdown": {k: f"{v/self.equity:.1%}" for k, v in asset_class_breakdown.items()},
            "max_heat_limit": self.config.max_portfolio_heat,
            "max_dd_limit": self.config.max_drawdown_pct,
        }

    def _calculate_portfolio_heat(self) -> float:
        """Calculate total portfolio heat as fraction of equity."""
        if self.equity <= 0:
            return 0.0
        total_risk = sum(p.risk_amount for p in self.positions)
        return total_risk / self.equity

    def _calculate_asset_heat(self, symbol: str) -> float:
        """Calculate heat for a specific asset."""
        if self.equity <= 0:
            return 0.0
        asset_risk = sum(p.risk_amount for p in self.positions if p.symbol == symbol)
        return asset_risk / self.equity

    def _calculate_asset_class_heat(self, asset_class: str) -> float:
        """Calculate heat for an asset class."""
        if self.equity <= 0:
            return 0.0
        class_risk = sum(
            p.risk_amount for p in self.positions
            if get_asset_config(p.symbol).asset_class == asset_class
        )
        return class_risk / self.equity

    def _calculate_correlated_exposure(self, symbol: str) -> float:
        """Calculate risk exposure from correlated assets."""
        if self._correlation_matrix is None or self._correlation_matrix.empty:
            return 0.0

        if symbol not in self._correlation_matrix.columns:
            return 0.0

        correlated_risk = 0.0
        for p in self.positions:
            if p.symbol == symbol:
                continue
            if p.symbol not in self._correlation_matrix.columns:
                continue
            corr = abs(self._correlation_matrix.loc[symbol, p.symbol])
            if corr > self.config.correlation_threshold:
                correlated_risk += p.risk_amount

        return correlated_risk

    def _calculate_drawdown(self) -> float:
        """Calculate current portfolio drawdown."""
        # Simplified: based on unrealized P&L
        if self.equity <= 0:
            return 0.0
        total_pnl = sum(p.unrealized_pnl for p in self.positions)
        peak_equity = self.equity - total_pnl  # Approximation
        if peak_equity <= 0:
            return 0.0
        return abs(total_pnl) / peak_equity if total_pnl < 0 else 0.0
