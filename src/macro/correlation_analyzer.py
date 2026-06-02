"""
Correlation analyzer for XAU/USD vs macro assets.

Calculates rolling correlation to validate macro assumptions.
"""

from __future__ import annotations

import pandas as pd

def calculate_rolling_correlation(
    xau_df: pd.DataFrame,
    macro_df: pd.DataFrame,
    window: int = 50,
    price_col: str = "Close",
) -> pd.Series:
    """
    Calculate rolling correlation between XAU/USD and a macro asset.

    Parameters:
    - xau_df: XAU/USD DataFrame
    - macro_df: Macro asset DataFrame (DXY, US10Y, etc.)
    - window: rolling window size
    - price_col: column name for price data

    Returns:
    - pd.Series of rolling correlation values
    """
    if xau_df.empty or macro_df.empty:
        return pd.Series(dtype=float)

    xau_prices = xau_df[price_col].reindex(macro_df.index, method="ffill")
    macro_prices = macro_df[price_col]

    aligned = pd.DataFrame({"xau": xau_prices, "macro": macro_prices}).dropna()

    if len(aligned) < window:
        return pd.Series(dtype=float)

    return aligned["xau"].rolling(window=window).corr(aligned["macro"])

def get_current_correlation(
    xau_df: pd.DataFrame,
    macro_df: pd.DataFrame,
    window: int = 50,
) -> float | None:
    """Get the most recent correlation value."""
    corr_series = calculate_rolling_correlation(xau_df, macro_df, window)
    if corr_series.empty or corr_series.isna().iloc[-1]:
        return None
    return float(corr_series.iloc[-1])

def is_correlation_valid(
    correlation: float | None,
    expected_sign: str,  # "negative" for DXY, "positive" for VIX
    threshold: float = 0.65,
) -> bool:
    """Check if correlation matches expected relationship."""
    if correlation is None:
        return False

    if expected_sign == "negative":
        return correlation <= -threshold
    elif expected_sign == "positive":
        return correlation >= threshold
    return False
