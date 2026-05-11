"""
Fast-loss proxy analysis for the final V50 balanced strategy.

Fast-loss labels use completed trades for diagnostics only. Candidate filter
features are validated so that only entry-known columns can be used.
"""

from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

from src.strategy_lab import strategy_v50_pine
from src.strategy_lab.strategy_v50_candidates import FINAL_BALANCED_STRATEGY_NAME
from src.strategy_lab.v50_loss_intelligence import prepare_balanced_loss_trades


DEFAULT_FAST_LOSS_PROXY_ANALYSIS_PATH = Path("reports/strategy_lab/v50_fast_loss_proxy_analysis.csv")
DEFAULT_FAST_LOSS_PROXY_CANDIDATES_PATH = Path("reports/strategy_lab/v50_fast_loss_proxy_candidates.csv")

FORBIDDEN_FILTER_COLUMNS = {
    "pnl",
    "profit_loss",
    "exit_time",
    "timestamp_close",
    "bars_in_trade",
    "trade_result",
    "result",
    "profit",
    "drawdown",
    "max_favorable_excursion",
    "max_adverse_excursion",
}
ENTRY_KNOWN_FILTER_COLUMNS = {
    "hour",
    "day_of_week",
    "session",
    "side_label",
    "side",
    "score_bucket",
    "score_gap_bucket",
    "signal_reason_bucket",
    "mode",
    "session_side",
    "hour_side",
    "hour_score_bucket",
    "session_score_bucket",
    "signal_reason_score_bucket",
}
PROXY_ANALYSIS_COLUMNS = [
    "group_name",
    "total_trades",
    "wins",
    "losses",
    "win_rate",
    "average_score",
    "average_score_gap",
    "average_adx",
    "average_rsi",
    "average_atr",
    "top_hours",
    "top_sessions",
    "top_sides",
    "top_score_buckets",
]
PROXY_CANDIDATE_COLUMNS = [
    "filter_column",
    "filter_value",
    "total_trades",
    "fast_loss_trades",
    "fast_loss_rate",
    "wins",
    "losses",
    "win_rate",
    "net_profit",
    "profit_factor",
    "average_trade",
    "leakage_safe",
]


def build_fast_loss_proxy_dataset(
    trades: pd.DataFrame,
    market_data: pd.DataFrame | None = None,
    strategy_name: str = FINAL_BALANCED_STRATEGY_NAME,
) -> pd.DataFrame:
    """Return V50 balanced trades with entry-known proxy features."""
    prepared = prepare_balanced_loss_trades(trades, strategy_name=strategy_name)
    if prepared.empty:
        return prepared

    result = prepared.copy()
    result["fast_loss"] = (pd.to_numeric(result["bars_in_trade"], errors="coerce") <= 1) & (result["pnl"] < 0)
    result["trade_group"] = "longer_trade"
    result.loc[result["pnl"] > 0, "trade_group"] = "winning_trade"
    result.loc[(result["pnl"] < 0) & ~result["fast_loss"], "trade_group"] = "normal_loss"
    result.loc[result["fast_loss"], "trade_group"] = "fast_loss_0_1"
    result["day_of_week"] = result["entry_time"].dt.day_name()
    result["score_gap"] = (
        pd.to_numeric(result.get("score_long"), errors="coerce")
        - pd.to_numeric(result.get("score_short"), errors="coerce")
    ).abs()
    result["score_gap_bucket"] = pd.cut(
        result["score_gap"].fillna(-1.0),
        bins=[-0.1, 7.999, 11.999, 19.999, 1000.0],
        labels=["gap_lt_8", "gap_8_11", "gap_12_19", "gap_20_plus"],
    ).astype("object").where(result["score_gap"].notna(), "gap_unknown")
    result["mode"] = result.get("signal_reason", pd.Series(index=result.index, dtype="object")).apply(_extract_mode)
    result["hour_side"] = result["hour"].astype(str) + "|" + result["side_label"].astype(str)
    result["hour_score_bucket"] = result["hour"].astype(str) + "|" + result["score_bucket"].astype(str)
    result["session_score_bucket"] = result["session"].astype(str) + "|" + result["score_bucket"].astype(str)
    result["signal_reason_score_bucket"] = (
        result["signal_reason_bucket"].astype(str) + "|" + result["score_bucket"].astype(str)
    )

    entry_features = _entry_market_features(market_data)
    if not entry_features.empty:
        result = pd.merge_asof(
            result.sort_values("entry_time"),
            entry_features.sort_values("entry_time"),
            on="entry_time",
            direction="backward",
        )

    return result.reset_index(drop=True)


def build_fast_loss_proxy_analysis(proxy_data: pd.DataFrame) -> pd.DataFrame:
    """Summarize fast losses vs wins and longer-duration trades."""
    if proxy_data.empty:
        return pd.DataFrame(columns=PROXY_ANALYSIS_COLUMNS)

    rows = []
    bars = pd.to_numeric(proxy_data.get("bars_in_trade"), errors="coerce")
    groups = {
        "fast_loss_0_1": proxy_data[proxy_data["trade_group"] == "fast_loss_0_1"].copy(),
        "normal_loss": proxy_data[proxy_data["trade_group"] == "normal_loss"].copy(),
        "winning_trade": proxy_data[proxy_data["trade_group"] == "winning_trade"].copy(),
        "longer_trade": proxy_data[bars > 1].copy(),
    }
    for group_name, group in groups.items():
        if group.empty:
            continue
        rows.append(_analysis_row(group_name, group))
    return pd.DataFrame(rows, columns=PROXY_ANALYSIS_COLUMNS)


def build_fast_loss_proxy_candidates(proxy_data: pd.DataFrame) -> pd.DataFrame:
    """Rank leakage-safe entry-known proxy patterns associated with fast losses."""
    if proxy_data.empty:
        return pd.DataFrame(columns=PROXY_CANDIDATE_COLUMNS)

    rows = []
    for column in sorted(ENTRY_KNOWN_FILTER_COLUMNS.intersection(proxy_data.columns)):
        validate_no_leakage_columns([column])
        for value, group in proxy_data.groupby(column, dropna=False):
            if len(group) < max(5, len(proxy_data) * 0.01):
                continue
            rows.append(_candidate_row(column, str(value), group))

    report = pd.DataFrame(rows, columns=PROXY_CANDIDATE_COLUMNS)
    if report.empty:
        return report
    return report.sort_values(
        ["fast_loss_rate", "net_profit", "total_trades"],
        ascending=[False, True, False],
    ).reset_index(drop=True)


def export_fast_loss_proxy_reports(
    analysis: pd.DataFrame,
    candidates: pd.DataFrame,
    analysis_path: str | Path = DEFAULT_FAST_LOSS_PROXY_ANALYSIS_PATH,
    candidates_path: str | Path = DEFAULT_FAST_LOSS_PROXY_CANDIDATES_PATH,
) -> tuple[Path, Path]:
    """Export fast-loss proxy analysis reports."""
    analysis_path = Path(analysis_path)
    candidates_path = Path(candidates_path)
    analysis_path.parent.mkdir(parents=True, exist_ok=True)
    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    analysis.to_csv(analysis_path, index=False)
    candidates.to_csv(candidates_path, index=False)
    return analysis_path, candidates_path


def validate_no_leakage_columns(columns: list[str] | tuple[str, ...] | set[str]) -> None:
    """Fail when candidate filter columns contain future/outcome information."""
    bad = []
    for column in columns:
        normalized = str(column).strip().lower()
        if normalized in FORBIDDEN_FILTER_COLUMNS:
            bad.append(column)
            continue
        if any(token in normalized for token in ["pnl", "exit", "profit", "drawdown", "favorable", "adverse"]):
            bad.append(column)
        if "bars_in_trade" in normalized or "trade_result" in normalized:
            bad.append(column)
    if bad:
        raise ValueError("Leakage filter columns are not allowed: " + ", ".join(sorted(map(str, bad))))


def _analysis_row(group_name: str, group: pd.DataFrame) -> dict:
    pnl = pd.to_numeric(group["pnl"], errors="coerce").fillna(0.0)
    wins = int((pnl > 0).sum())
    losses = int((pnl < 0).sum())
    return {
        "group_name": group_name,
        "total_trades": int(len(group)),
        "wins": wins,
        "losses": losses,
        "win_rate": wins / len(group) * 100 if len(group) else 0.0,
        "average_score": _mean(group.get("score_value")),
        "average_score_gap": _mean(group.get("score_gap")),
        "average_adx": _mean(group.get("entry_adx")),
        "average_rsi": _mean(group.get("entry_rsi")),
        "average_atr": _mean(group.get("entry_atr")),
        "top_hours": _top_values(group, "hour"),
        "top_sessions": _top_values(group, "session"),
        "top_sides": _top_values(group, "side_label"),
        "top_score_buckets": _top_values(group, "score_bucket"),
    }


def _candidate_row(column: str, value: str, group: pd.DataFrame) -> dict:
    pnl = pd.to_numeric(group["pnl"], errors="coerce").fillna(0.0)
    wins = int((pnl > 0).sum())
    losses = int((pnl < 0).sum())
    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = float(abs(pnl[pnl < 0].sum()))
    total = int(len(group))
    fast_losses = int(group["fast_loss"].sum())
    return {
        "filter_column": column,
        "filter_value": value,
        "total_trades": total,
        "fast_loss_trades": fast_losses,
        "fast_loss_rate": fast_losses / total * 100 if total else 0.0,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / total * 100 if total else 0.0,
        "net_profit": float(pnl.sum()),
        "profit_factor": _profit_factor(gross_profit, gross_loss),
        "average_trade": float(pnl.mean()) if total else 0.0,
        "leakage_safe": True,
    }


def _entry_market_features(market_data: pd.DataFrame | None) -> pd.DataFrame:
    if market_data is None or market_data.empty:
        return pd.DataFrame()

    features = strategy_v50_pine.build_v50_features(market_data)
    result = pd.DataFrame(index=features.index)
    result["entry_time"] = features.index
    result["entry_candle_body"] = (features["Close"] - features["Open"]).abs()
    result["entry_candle_range"] = features["High"] - features["Low"]
    result["entry_body_to_range_ratio"] = result["entry_candle_body"] / result["entry_candle_range"].where(
        result["entry_candle_range"] != 0
    )
    result["entry_adx"] = features.get("v50_adx")
    result["entry_rsi"] = features.get("v50_rsi")
    result["entry_atr"] = features.get("v50_atr")
    return result.reset_index(drop=True).replace([float("inf"), float("-inf")], pd.NA)


def _extract_mode(reason: object) -> str:
    if not isinstance(reason, str):
        return "unknown"
    match = re.search(r"(?:^|\|\s*)mode\s*=\s*([^|]+)", reason, flags=re.IGNORECASE)
    return match.group(1).strip() if match else "unknown"


def _top_values(group: pd.DataFrame, column: str, limit: int = 3) -> str:
    if column not in group.columns:
        return ""
    counts = group[column].astype(str).value_counts().head(limit)
    return "; ".join(f"{index}:{value}" for index, value in counts.items())


def _mean(series: pd.Series | None) -> float:
    if series is None:
        return float("nan")
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if len(values) else float("nan")


def _profit_factor(gross_profit: float, gross_loss: float) -> float:
    if gross_loss > 0:
        return gross_profit / gross_loss
    if gross_profit > 0:
        return float("inf")
    return 0.0
