"""
Feature engineering for ML model from trade history.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


def extract_features_from_trade_row(row: pd.Series) -> dict[str, Any]:
    """Extract ML features from a single trade DataFrame row."""
    features = {}

    features["adx_at_entry"] = float(row.get("adx_at_entry", row.get("ADX_14", 20)))
    features["rsi_at_entry"] = float(row.get("rsi_at_entry", row.get("RSI_14", 50)))
    features["ema_distance_pct"] = float(row.get("ema_distance_pct", 0.0))
    features["atr_pct"] = float(row.get("atr_pct", 0.01))
    features["risk_reward"] = float(row.get("risk_reward", 2.0))
    features["macro_score"] = float(row.get("macro_score", 0.0))
    features["dxy_correlation"] = float(row.get("dxy_correlation", 0.0))
    features["smc_score"] = float(row.get("smc_score", 0.0))
    features["fvg_aligned"] = int(row.get("fvg_aligned", 0))
    features["ob_nearby"] = int(row.get("ob_nearby", 0))
    features["sweep_confirmed"] = int(row.get("sweep_confirmed", 0))

    session = str(row.get("session", "Off Session"))
    features["session_london"] = 1 if session == "London" else 0
    features["session_ny"] = 1 if session == "New York" else 0
    features["session_asia"] = 1 if session == "Asia" else 0

    features["trend_aligned"] = int(row.get("trend_aligned", 1))
    features["structure_bos"] = int(row.get("structure_bos", 0))

    outcome = float(row.get("outcome", 0.0))
    features["outcome"] = outcome
    features["won"] = 1 if outcome > 0 else 0

    return features


def build_feature_matrix(trades_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Build feature matrix X and target y from trades DataFrame."""
    if trades_df.empty:
        return pd.DataFrame(), pd.Series(dtype=int)

    features_list = []
    for _, row in trades_df.iterrows():
        features_list.append(extract_features_from_trade_row(row))

    df = pd.DataFrame(features_list)

    feature_cols = [
        "adx_at_entry", "rsi_at_entry", "ema_distance_pct", "atr_pct", "risk_reward",
        "macro_score", "dxy_correlation", "smc_score", "fvg_aligned", "ob_nearby",
        "sweep_confirmed", "session_london", "session_ny", "session_asia",
        "trend_aligned", "structure_bos",
    ]

    X = df[feature_cols].fillna(0)
    y = df["won"]

    return X, y
