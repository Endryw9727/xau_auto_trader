"""
Multi-asset registry for XAU Auto Trader.

Manages symbols, timeframes, and asset-specific configurations
for XAU/USD, EUR/USD, GBP/USD, BTC/USD, and other instruments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AssetClass = Literal["forex", "crypto", "commodity", "index"]

@dataclass(frozen=True)
class AssetConfig:
    """Configuration for a specific trading instrument."""

    symbol: str
    display_name: str
    asset_class: AssetClass
    base_currency: str
    quote_currency: str
    pip_value: float  # Value per pip/point in quote currency
    pip_decimal_places: int  # Decimal places for pip calculation
    default_spread_points: float
    default_lot_size: float
    min_lot_size: float
    max_lot_size: float
    leverage_default: float
    trading_hours: str  # "24/5", "24/7", "exchange"
    volatility_profile: str  # "low", "medium", "high", "extreme"
    session_relevance: dict[str, float]  # Session importance weights

    # Strategy overrides
    atr_multiplier_sl: float | None = None
    atr_multiplier_tp: float | None = None
    rsi_buy_max: float | None = None
    rsi_sell_min: float | None = None
    min_adx: float | None = None
    min_risk_reward: float | None = None


# Pre-configured asset definitions
ASSET_REGISTRY: dict[str, AssetConfig] = {
    "XAUUSD": AssetConfig(
        symbol="XAUUSD",
        display_name="Gold vs US Dollar",
        asset_class="commodity",
        base_currency="XAU",
        quote_currency="USD",
        pip_value=1.0,
        pip_decimal_places=2,
        default_spread_points=20.0,
        default_lot_size=0.01,
        min_lot_size=0.01,
        max_lot_size=50.0,
        leverage_default=100.0,
        trading_hours="24/5",
        volatility_profile="high",
        session_relevance={
            "London": 1.0,
            "New York": 0.95,
            "Asia": 0.6,
            "Off Session": 0.3,
        },
        atr_multiplier_sl=1.5,
        atr_multiplier_tp=3.0,
        rsi_buy_max=70.0,
        rsi_sell_min=30.0,
        min_adx=18.0,
        min_risk_reward=2.0,
    ),
    "EURUSD": AssetConfig(
        symbol="EURUSD",
        display_name="Euro vs US Dollar",
        asset_class="forex",
        base_currency="EUR",
        quote_currency="USD",
        pip_value=10.0,
        pip_decimal_places=4,
        default_spread_points=1.0,
        default_lot_size=0.1,
        min_lot_size=0.01,
        max_lot_size=100.0,
        leverage_default=500.0,
        trading_hours="24/5",
        volatility_profile="medium",
        session_relevance={
            "London": 1.0,
            "New York": 0.9,
            "Asia": 0.5,
            "Off Session": 0.2,
        },
        atr_multiplier_sl=1.0,
        atr_multiplier_tp=2.0,
        rsi_buy_max=65.0,
        rsi_sell_min=35.0,
        min_adx=20.0,
        min_risk_reward=1.5,
    ),
    "GBPUSD": AssetConfig(
        symbol="GBPUSD",
        display_name="British Pound vs US Dollar",
        asset_class="forex",
        base_currency="GBP",
        quote_currency="USD",
        pip_value=10.0,
        pip_decimal_places=4,
        default_spread_points=2.0,
        default_lot_size=0.1,
        min_lot_size=0.01,
        max_lot_size=100.0,
        leverage_default=500.0,
        trading_hours="24/5",
        volatility_profile="high",
        session_relevance={
            "London": 1.0,
            "New York": 0.85,
            "Asia": 0.4,
            "Off Session": 0.2,
        },
        atr_multiplier_sl=1.2,
        atr_multiplier_tp=2.5,
        rsi_buy_max=68.0,
        rsi_sell_min=32.0,
        min_adx=20.0,
        min_risk_reward=1.8,
    ),
    "BTCUSD": AssetConfig(
        symbol="BTCUSD",
        display_name="Bitcoin vs US Dollar",
        asset_class="crypto",
        base_currency="BTC",
        quote_currency="USD",
        pip_value=1.0,
        pip_decimal_places=2,
        default_spread_points=50.0,
        default_lot_size=0.01,
        min_lot_size=0.001,
        max_lot_size=10.0,
        leverage_default=20.0,
        trading_hours="24/7",
        volatility_profile="extreme",
        session_relevance={
            "London": 0.7,
            "New York": 0.9,
            "Asia": 0.8,
            "Off Session": 0.6,
        },
        atr_multiplier_sl=2.0,
        atr_multiplier_tp=4.0,
        rsi_buy_max=75.0,
        rsi_sell_min=25.0,
        min_adx=15.0,
        min_risk_reward=2.5,
    ),
    "USDJPY": AssetConfig(
        symbol="USDJPY",
        display_name="US Dollar vs Japanese Yen",
        asset_class="forex",
        base_currency="USD",
        quote_currency="JPY",
        pip_value=1000.0,
        pip_decimal_places=2,
        default_spread_points=1.0,
        default_lot_size=0.1,
        min_lot_size=0.01,
        max_lot_size=100.0,
        leverage_default=500.0,
        trading_hours="24/5",
        volatility_profile="medium",
        session_relevance={
            "London": 0.8,
            "New York": 0.9,
            "Asia": 1.0,
            "Off Session": 0.3,
        },
        atr_multiplier_sl=1.0,
        atr_multiplier_tp=2.0,
        rsi_buy_max=65.0,
        rsi_sell_min=35.0,
        min_adx=20.0,
        min_risk_reward=1.5,
    ),
}


def get_asset_config(symbol: str) -> AssetConfig:
    """Get configuration for a symbol."""
    symbol_upper = symbol.upper().replace("-", "").replace("/", "")
    if symbol_upper in ASSET_REGISTRY:
        return ASSET_REGISTRY[symbol_upper]

    # Default config for unknown symbols
    return AssetConfig(
        symbol=symbol,
        display_name=symbol,
        asset_class="forex",
        base_currency=symbol[:3],
        quote_currency=symbol[3:],
        pip_value=1.0,
        pip_decimal_places=4,
        default_spread_points=2.0,
        default_lot_size=0.1,
        min_lot_size=0.01,
        max_lot_size=100.0,
        leverage_default=100.0,
        trading_hours="24/5",
        volatility_profile="medium",
        session_relevance={
            "London": 0.8,
            "New York": 0.8,
            "Asia": 0.5,
            "Off Session": 0.3,
        },
    )


def list_available_assets() -> list[str]:
    """List all available asset symbols."""
    return list(ASSET_REGISTRY.keys())


def get_asset_specific_strategy_config(symbol: str, base_config: dict) -> dict:
    """Override base strategy config with asset-specific parameters."""
    asset = get_asset_config(symbol)
    config = base_config.copy()

    if asset.atr_multiplier_sl is not None:
        config["atr_multiplier_sl"] = asset.atr_multiplier_sl
    if asset.atr_multiplier_tp is not None:
        config["atr_multiplier_tp"] = asset.atr_multiplier_tp
    if asset.rsi_buy_max is not None:
        config["rsi_buy_max"] = asset.rsi_buy_max
    if asset.rsi_sell_min is not None:
        config["rsi_sell_min"] = asset.rsi_sell_min
    if asset.min_adx is not None:
        config["min_adx"] = asset.min_adx
    if asset.min_risk_reward is not None:
        config["min_risk_reward"] = asset.min_risk_reward

    return config
