"""
Trade outcome analysis for research/backtesting.

This module links backtest trades to market features observed near trade entry
and summarizes outcomes by feature buckets. It does not execute trades and does
not interact with brokers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


GROUP_COLUMNS = [
    "session",
    "trend_regime",
    "volatility_regime",
    "candle_regime",
    "side",
    "adx_bucket",
    "rsi_bucket",
    "williams_r_bucket",
    "distance_from_ema20_bucket",
    "atr_ratio_bucket",
]


def analyze_trade_outcomes(trades: pd.DataFrame, features: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Link trades to nearest entry-time features and build grouped summaries.

    Returns a dictionary with:
    - trade_feature_dataset: one row per trade plus nearest feature row
    - outcome_by_<group>: grouped outcome tables
    """
    enriched = build_trade_feature_dataset(trades, features)
    enriched = add_feature_buckets(enriched)

    summaries = {
        f"outcome_by_{group_column}": summarize_outcomes_by(enriched, group_column)
        for group_column in GROUP_COLUMNS
        if group_column in enriched.columns
    }

    return {
        "trade_feature_dataset": enriched,
        **summaries,
    }


def build_trade_feature_dataset(trades: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Attach nearest feature row to every trade by timestamp_open."""
    _validate_trades(trades)

    if trades.empty:
        return trades.copy()

    feature_frame = _prepare_features_for_join(features)

    if feature_frame.empty:
        raise ValueError("features DataFrame cannot be empty")

    trade_frame = trades.copy()
    trade_frame["timestamp_open"] = pd.to_datetime(trade_frame["timestamp_open"], errors="coerce")
    trade_frame = trade_frame.dropna(subset=["timestamp_open"]).sort_values("timestamp_open")
    trade_frame["_trade_order"] = range(len(trade_frame))

    enriched = pd.merge_asof(
        trade_frame,
        feature_frame,
        left_on="timestamp_open",
        right_on="feature_timestamp",
        direction="nearest",
    )

    enriched = enriched.sort_values("_trade_order").drop(columns=["_trade_order"])
    return enriched.reset_index(drop=True)


def add_feature_buckets(enriched: pd.DataFrame) -> pd.DataFrame:
    """Add numeric feature buckets used for outcome summaries."""
    result = enriched.copy()

    if "adx" in result.columns:
        result["adx_bucket"] = pd.cut(
            pd.to_numeric(result["adx"], errors="coerce"),
            bins=[-np.inf, 18, 25, 35, np.inf],
            labels=["weak", "moderate", "strong", "very_strong"],
        ).astype("object")

    if "rsi" in result.columns:
        result["rsi_bucket"] = pd.cut(
            pd.to_numeric(result["rsi"], errors="coerce"),
            bins=[-np.inf, 30, 45, 55, 70, np.inf],
            labels=["oversold", "bearish", "neutral", "bullish", "overbought"],
        ).astype("object")

    if "williams_r" in result.columns:
        result["williams_r_bucket"] = pd.cut(
            pd.to_numeric(result["williams_r"], errors="coerce"),
            bins=[-np.inf, -80, -50, -20, np.inf],
            labels=["oversold", "bearish_mid", "bullish_mid", "overbought"],
        ).astype("object")

    if "distance_from_ema20" in result.columns:
        result["distance_from_ema20_bucket"] = pd.cut(
            pd.to_numeric(result["distance_from_ema20"], errors="coerce"),
            bins=[-np.inf, -1.0, -0.25, 0.25, 1.0, np.inf],
            labels=["far_below", "below", "near", "above", "far_above"],
        ).astype("object")

    if "atr_ratio" in result.columns:
        result["atr_ratio_bucket"] = _quantile_bucket(
            pd.to_numeric(result["atr_ratio"], errors="coerce"),
            labels=["low", "normal", "high"],
        )

    return result


def summarize_outcomes_by(enriched: pd.DataFrame, group_column: str) -> pd.DataFrame:
    """Summarize trade outcomes by one grouping column."""
    _validate_enriched_for_summary(enriched, group_column)

    if enriched.empty:
        return _empty_summary(group_column)

    result = enriched.copy()
    result["profit_loss"] = pd.to_numeric(result["profit_loss"], errors="coerce").fillna(0.0)
    result[group_column] = result[group_column].astype("object").where(result[group_column].notna(), "Unknown")

    rows = []

    for group_value, group in result.groupby(group_column, dropna=False):
        pnl = group["profit_loss"]
        wins = int((pnl > 0).sum())
        losses = int((pnl < 0).sum())
        gross_profit = float(pnl[pnl > 0].sum())
        gross_loss = float(abs(pnl[pnl < 0].sum()))

        rows.append(
            {
                group_column: group_value,
                "total_trades": int(len(group)),
                "wins": wins,
                "losses": losses,
                "win_rate": wins / len(group) * 100 if len(group) else 0.0,
                "net_profit": float(pnl.sum()),
                "average_trade": float(pnl.mean()) if len(group) else 0.0,
                "profit_factor": _calculate_profit_factor(gross_profit, gross_loss),
                "max_loss": float(pnl.min()) if len(group) else 0.0,
                "max_win": float(pnl.max()) if len(group) else 0.0,
            }
        )

    summary = pd.DataFrame(rows)
    return summary.sort_values(["profit_factor", "net_profit"], ascending=[False, False], na_position="last").reset_index(drop=True)


def _calculate_profit_factor(gross_profit: float, gross_loss: float) -> float | None:
    """Calculate profit factor when enough loss data exists."""
    if gross_loss == 0:
        return None

    return gross_profit / gross_loss


def _prepare_features_for_join(features: pd.DataFrame) -> pd.DataFrame:
    """Normalize features to a sorted frame with feature_timestamp column."""
    if features.empty:
        return features.copy()

    result = features.copy()

    if isinstance(result.index, pd.DatetimeIndex):
        result["feature_timestamp"] = result.index
    elif "Date" in result.columns:
        result["feature_timestamp"] = pd.to_datetime(result["Date"], errors="coerce")
    elif "timestamp" in result.columns:
        result["feature_timestamp"] = pd.to_datetime(result["timestamp"], errors="coerce")
    else:
        first_column = result.columns[0]
        parsed = pd.to_datetime(result[first_column], errors="coerce")

        if parsed.notna().any():
            result["feature_timestamp"] = parsed
        else:
            raise ValueError("features must have a DatetimeIndex or timestamp-like column")

    result["feature_timestamp"] = pd.to_datetime(result["feature_timestamp"], errors="coerce")
    result = result.dropna(subset=["feature_timestamp"]).sort_values("feature_timestamp")

    return result.reset_index(drop=True)


def _quantile_bucket(values: pd.Series, labels: list[str]) -> pd.Series:
    """Bucket a numeric series into quantile labels with safe fallbacks."""
    non_null = values.dropna()

    if non_null.empty:
        return pd.Series([np.nan] * len(values), index=values.index, dtype="object")

    unique_count = non_null.nunique()

    if unique_count < len(labels):
        return pd.Series(["normal" if pd.notna(value) else np.nan for value in values], index=values.index, dtype="object")

    try:
        return pd.qcut(values, q=len(labels), labels=labels, duplicates="drop").astype("object")
    except ValueError:
        return pd.Series(["normal" if pd.notna(value) else np.nan for value in values], index=values.index, dtype="object")


def _validate_trades(trades: pd.DataFrame) -> None:
    """Validate trade columns required for outcome analysis."""
    required = ["timestamp_open", "side", "profit_loss"]
    missing = [column for column in required if column not in trades.columns]

    if missing:
        raise ValueError(f"Missing required trade columns: {missing}")


def _validate_enriched_for_summary(enriched: pd.DataFrame, group_column: str) -> None:
    """Validate columns required for grouped outcome summaries."""
    missing = [column for column in [group_column, "profit_loss"] if column not in enriched.columns]

    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def _empty_summary(group_column: str) -> pd.DataFrame:
    """Return an empty summary with stable columns."""
    return pd.DataFrame(
        columns=[
            group_column,
            "total_trades",
            "wins",
            "losses",
            "win_rate",
            "net_profit",
            "average_trade",
            "profit_factor",
            "max_loss",
            "max_win",
        ]
    )
