"""
Multi-asset data feed manager.

Manages loading and resampling data for multiple instruments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.data_feed.market_data import load_csv_data, resample_data
from src.market_data.asset_registry import AssetConfig, get_asset_config


class MultiAssetDataFeed:
    """Manages data feeds for multiple trading instruments."""

    def __init__(self, data_dir: Path = Path("data/raw")):
        self.data_dir = data_dir
        self._cache: dict[str, pd.DataFrame] = {}
        self._assets: dict[str, AssetConfig] = {}

    def load_asset(self, symbol: str, timeframe: str = "15m") -> pd.DataFrame:
        """Load data for a specific asset and timeframe."""
        cache_key = f"{symbol}_{timeframe}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try multiple filename patterns
        patterns = [
            f"{symbol.lower()}.csv",
            f"{symbol.upper()}.csv",
            f"{symbol.lower()}_{timeframe}.csv",
            f"{symbol.upper()}_{timeframe}.csv",
            f"timeframes/{symbol.upper()}_{timeframe.upper()}.csv",
        ]

        for pattern in patterns:
            path = self.data_dir / pattern
            if path.exists():
                df = load_csv_data(path)
                if timeframe != "raw":
                    df = resample_data(df, self._timeframe_to_pandas(timeframe))
                self._cache[cache_key] = df
                self._assets[symbol] = get_asset_config(symbol)
                return df

        raise FileNotFoundError(f"No data found for {symbol} in {self.data_dir}")

    def get_asset_info(self, symbol: str) -> AssetConfig:
        """Get asset configuration."""
        if symbol not in self._assets:
            self._assets[symbol] = get_asset_config(symbol)
        return self._assets[symbol]

    def get_all_assets(self) -> dict[str, pd.DataFrame]:
        """Get all loaded assets."""
        return dict(self._cache)

    def refresh(self, symbol: str | None = None) -> None:
        """Refresh cached data."""
        if symbol:
            keys = [k for k in self._cache if k.startswith(f"{symbol}_")]
            for k in keys:
                del self._cache[k]
        else:
            self._cache.clear()

    @staticmethod
    def _timeframe_to_pandas(timeframe: str) -> str:
        """Convert trading timeframe to pandas offset."""
        mapping = {
            "1m": "1min",
            "5m": "5min",
            "15m": "15min",
            "30m": "30min",
            "1h": "1H",
            "4h": "4H",
            "1d": "1D",
            "1w": "1W",
        }
        return mapping.get(timeframe, timeframe)

    def get_correlation_matrix(self) -> pd.DataFrame | None:
        """Calculate correlation matrix between loaded assets."""
        if len(self._cache) < 2:
            return None

        closes = {}
        for key, df in self._cache.items():
            symbol = key.split("_")[0]
            closes[symbol] = df["Close"]

        corr_df = pd.DataFrame(closes)
        return corr_df.corr()
