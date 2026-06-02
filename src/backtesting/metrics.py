"""
Metrics utilities for backtest reporting.
"""

from __future__ import annotations

import pandas as pd

def metrics_to_dict(metrics_df: pd.DataFrame) -> dict[str, float | int]:
    """Convert metrics DataFrame to a dictionary."""
    return dict(zip(metrics_df["metric"], metrics_df["value"]))
