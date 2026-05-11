"""
Loss intelligence helpers for the final V50 balanced candidate.

The module works on simulated backtest trades and optional local market data.
It is intended for research diagnostics and counterfactual filtering only.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.analysis.trade_level_diagnostics import prepare_trade_report
from src.backtesting.metrics import BacktestMetrics, calculate_max_consecutive, calculate_metrics, metrics_to_dict
from src.strategy_lab.strategy_v50_candidates import FINAL_BALANCED_STRATEGY_NAME
from src.strategy_lab.v50_daily_coverage import build_daily_breakdown, build_daily_coverage_report


DEFAULT_LOSS_CLUSTERS_PATH = Path("reports/strategy_lab/v50_loss_clusters.csv")
DEFAULT_LOSS_BREAKDOWN_PATH = Path("reports/strategy_lab/v50_loss_breakdown.csv")
DEFAULT_LOSS_PATTERN_CANDIDATES_PATH = Path("reports/strategy_lab/v50_loss_pattern_candidates.csv")
TRADES_BY_STRATEGY_PATH = Path("reports/backtests/trades_by_strategy.csv")
TRADES_PATH = Path("reports/backtests/trades.csv")

SCORE_BUCKETS = [-0.1, 69.999, 74.999, 79.999, 84.999, 1000.0]
SCORE_LABELS = ["score_lt_70", "score_70_74", "score_75_79", "score_80_84", "score_85_plus"]
BARS_BUCKETS = [-0.1, 1.0, 3.0, 7.0, 15.0, 30.0, 100000.0]
BARS_LABELS = ["bars_0_1", "bars_2_3", "bars_4_7", "bars_8_15", "bars_16_30", "bars_31_plus"]
LOSS_CLUSTER_COLUMNS = [
    "cluster_id",
    "start_time",
    "end_time",
    "loss_count",
    "net_loss",
    "worst_trade",
    "session_dominant",
    "side_dominant",
    "average_score_long",
    "average_score_short",
    "average_bars_in_trade",
]
LOSS_BREAKDOWN_COLUMNS = [
    "pattern_type",
    "pattern_value",
    "total_trades",
    "wins",
    "losses",
    "win_rate",
    "profit_factor",
    "net_profit",
    "max_drawdown_estimated",
    "average_trade",
    "gross_profit",
    "gross_loss",
    "loss_share",
]
PATTERN_CANDIDATE_COLUMNS = [
    "pattern_type",
    "pattern_value",
    "removed_trades",
    "remaining_trades",
    "removed_trade_pct",
    "base_profit_factor",
    "new_profit_factor",
    "base_max_drawdown",
    "new_max_drawdown",
    "base_net_profit",
    "new_net_profit",
    "average_trades_per_day",
    "active_day_ratio",
    "improves_pf",
    "improves_dd",
    "leaves_min_trades",
    "leaves_min_daily_frequency",
    "candidate_pass",
]


def load_loss_trade_report(paths: tuple[Path, ...] = (TRADES_BY_STRATEGY_PATH, TRADES_PATH)) -> pd.DataFrame | None:
    """Load the first available strategy-tagged trade report."""
    for path in paths:
        if not path.exists():
            continue
        trades = pd.read_csv(path)
        if "strategy_name" in trades.columns and ("pnl" in trades.columns or "profit_loss" in trades.columns):
            return trades
    return None


def prepare_balanced_loss_trades(
    trades: pd.DataFrame,
    strategy_name: str = FINAL_BALANCED_STRATEGY_NAME,
) -> pd.DataFrame:
    """Return V50 balanced trades with loss-intelligence buckets."""
    prepared = prepare_trade_report(trades)
    if prepared.empty or "strategy_name" not in prepared.columns:
        return pd.DataFrame()

    result = prepared[prepared["strategy_name"] == strategy_name].copy()
    if result.empty:
        return result

    result["entry_time"] = pd.to_datetime(result["entry_time"], errors="coerce")
    result = result.dropna(subset=["entry_time"]).sort_values("entry_time").reset_index(drop=True)
    result["pnl"] = pd.to_numeric(result["pnl"], errors="coerce").fillna(0.0)
    result["profit_loss"] = result["pnl"]
    result["hour"] = result["entry_time"].dt.hour
    result["weekday"] = result["entry_time"].dt.day_name()
    result["month"] = result["entry_time"].dt.to_period("M").astype("string")
    result["year"] = result["entry_time"].dt.year.astype("Int64").astype("string")
    result["session"] = _column_or_default(result, "session", "Unknown")
    result["side_label"] = _column_or_default(result, "side_label", None)
    if result["side_label"].eq("Unknown").all() and "side" in result.columns:
        result["side_label"] = result["side"].map({"BUY": "LONG", "SELL": "SHORT"}).fillna("Unknown")
    result["session_side"] = result["session"].astype(str) + "|" + result["side_label"].astype(str)
    result["score_value"] = _side_score(result)
    result["score_bucket"] = pd.cut(
        result["score_value"],
        bins=SCORE_BUCKETS,
        labels=SCORE_LABELS,
    ).astype("object").where(result["score_value"].notna(), "score_unknown")
    result["bars_in_trade"] = pd.to_numeric(result.get("bars_in_trade", pd.Series(index=result.index)), errors="coerce")
    result["bars_in_trade_bucket"] = pd.cut(
        result["bars_in_trade"].fillna(-1.0),
        bins=BARS_BUCKETS,
        labels=BARS_LABELS,
    ).astype("object").where(result["bars_in_trade"].notna(), "bars_unknown")
    result["signal_reason_bucket"] = result.get("signal_reason", pd.Series(index=result.index, dtype="object")).fillna(
        "Unknown"
    ).astype(str).str.split("|", n=1).str[0].str.strip()
    return result


def build_loss_clusters(trades: pd.DataFrame, min_losses: int = 2) -> pd.DataFrame:
    """Find consecutive losing-trade clusters."""
    if trades.empty:
        return pd.DataFrame(columns=LOSS_CLUSTER_COLUMNS)

    clusters = []
    current = []
    for _, row in trades.sort_values("entry_time").iterrows():
        if float(row["pnl"]) < 0:
            current.append(row)
            continue
        _append_cluster(clusters, current, min_losses)
        current = []
    _append_cluster(clusters, current, min_losses)

    return pd.DataFrame(clusters, columns=LOSS_CLUSTER_COLUMNS)


def build_loss_breakdown(trades: pd.DataFrame) -> pd.DataFrame:
    """Build grouped loss/profit breakdown tables."""
    if trades.empty:
        return pd.DataFrame(columns=LOSS_BREAKDOWN_COLUMNS)

    total_gross_loss = float(abs(trades.loc[trades["pnl"] < 0, "pnl"].sum()))
    rows = []
    for pattern_type, column in [
        ("hour", "hour"),
        ("weekday", "weekday"),
        ("month", "month"),
        ("session", "session"),
        ("side", "side_label"),
        ("session_side", "session_side"),
        ("score_bucket", "score_bucket"),
        ("bars_in_trade_bucket", "bars_in_trade_bucket"),
        ("signal_reason", "signal_reason_bucket"),
    ]:
        if column not in trades.columns:
            continue
        for value, group in trades.groupby(column, dropna=False):
            rows.append(_breakdown_row(pattern_type, str(value), group, total_gross_loss))

    return pd.DataFrame(rows, columns=LOSS_BREAKDOWN_COLUMNS).sort_values(
        ["net_profit", "total_trades"],
        ascending=[True, False],
    ).reset_index(drop=True)


def build_loss_pattern_candidates(
    trades: pd.DataFrame,
    breakdown: pd.DataFrame,
    market_data: pd.DataFrame | None = None,
    min_trades: int = 700,
    min_average_trades_per_day: float = 0.75,
) -> pd.DataFrame:
    """Return patterns whose removal improves PF and drawdown while preserving coverage."""
    if trades.empty or breakdown.empty:
        return pd.DataFrame(columns=PATTERN_CANDIDATE_COLUMNS)

    base_metrics = calculate_metrics(trades, initial_balance=1000.0)
    base_dict = metrics_to_dict(base_metrics)
    rows = []

    for _, pattern in breakdown.iterrows():
        pattern_type = str(pattern["pattern_type"])
        pattern_value = str(pattern["pattern_value"])
        mask = _pattern_mask(trades, pattern_type, pattern_value)
        if not mask.any() or mask.all():
            continue

        remaining = trades.loc[~mask].copy().reset_index(drop=True)
        metrics = calculate_metrics(remaining, initial_balance=1000.0)
        metrics_dict = metrics_to_dict(metrics)
        daily = _coverage_row(remaining, market_data)
        removed_trades = int(mask.sum())
        remaining_trades = int(metrics_dict["total_trades"])
        average_trades = float(daily.get("average_trades_per_day", 0.0))
        improves_pf = float(metrics_dict["profit_factor"]) > float(base_dict["profit_factor"])
        improves_dd = float(metrics_dict["max_drawdown"]) < float(base_dict["max_drawdown"])
        leaves_min_trades = remaining_trades >= min_trades
        leaves_min_daily_frequency = average_trades >= min_average_trades_per_day

        rows.append(
            {
                "pattern_type": pattern_type,
                "pattern_value": pattern_value,
                "removed_trades": removed_trades,
                "remaining_trades": remaining_trades,
                "removed_trade_pct": removed_trades / len(trades) if len(trades) else 0.0,
                "base_profit_factor": base_dict["profit_factor"],
                "new_profit_factor": metrics_dict["profit_factor"],
                "base_max_drawdown": base_dict["max_drawdown"],
                "new_max_drawdown": metrics_dict["max_drawdown"],
                "base_net_profit": base_dict["net_profit"],
                "new_net_profit": metrics_dict["net_profit"],
                "average_trades_per_day": average_trades,
                "active_day_ratio": float(daily.get("active_day_ratio", 0.0)),
                "improves_pf": improves_pf,
                "improves_dd": improves_dd,
                "leaves_min_trades": leaves_min_trades,
                "leaves_min_daily_frequency": leaves_min_daily_frequency,
                "candidate_pass": (
                    improves_pf
                    and improves_dd
                    and leaves_min_trades
                    and leaves_min_daily_frequency
                    and float(metrics_dict["net_profit"]) > 0
                ),
            }
        )

    return pd.DataFrame(rows, columns=PATTERN_CANDIDATE_COLUMNS).sort_values(
        ["candidate_pass", "new_profit_factor", "new_max_drawdown"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def export_loss_intelligence_reports(
    clusters: pd.DataFrame,
    breakdown: pd.DataFrame,
    candidates: pd.DataFrame,
    clusters_path: str | Path = DEFAULT_LOSS_CLUSTERS_PATH,
    breakdown_path: str | Path = DEFAULT_LOSS_BREAKDOWN_PATH,
    candidates_path: str | Path = DEFAULT_LOSS_PATTERN_CANDIDATES_PATH,
) -> tuple[Path, Path, Path]:
    """Export loss-intelligence CSV reports."""
    clusters_path = Path(clusters_path)
    breakdown_path = Path(breakdown_path)
    candidates_path = Path(candidates_path)
    for path in [clusters_path, breakdown_path, candidates_path]:
        path.parent.mkdir(parents=True, exist_ok=True)
    clusters.to_csv(clusters_path, index=False)
    breakdown.to_csv(breakdown_path, index=False)
    candidates.to_csv(candidates_path, index=False)
    return clusters_path, breakdown_path, candidates_path


def max_consecutive_losses(trades: pd.DataFrame) -> int:
    """Return maximum consecutive losses for a prepared trade set."""
    if trades.empty or "pnl" not in trades.columns:
        return 0
    return calculate_max_consecutive(pd.to_numeric(trades["pnl"], errors="coerce").fillna(0.0), positive=False)


def _append_cluster(clusters: list[dict], current: list[pd.Series], min_losses: int) -> None:
    if len(current) < min_losses:
        return

    cluster = pd.DataFrame(current)
    pnl = pd.to_numeric(cluster["pnl"], errors="coerce").fillna(0.0)
    clusters.append(
        {
            "cluster_id": len(clusters) + 1,
            "start_time": cluster["entry_time"].iloc[0],
            "end_time": cluster["entry_time"].iloc[-1],
            "loss_count": int(len(cluster)),
            "net_loss": float(pnl.sum()),
            "worst_trade": float(pnl.min()),
            "session_dominant": _mode_value(cluster.get("session")),
            "side_dominant": _mode_value(cluster.get("side_label")),
            "average_score_long": _mean_optional(cluster.get("score_long")),
            "average_score_short": _mean_optional(cluster.get("score_short")),
            "average_bars_in_trade": _mean_optional(cluster.get("bars_in_trade")),
        }
    )


def _breakdown_row(pattern_type: str, pattern_value: str, group: pd.DataFrame, total_gross_loss: float) -> dict:
    metrics = calculate_metrics(group, initial_balance=1000.0)
    metrics_dict = metrics_to_dict(metrics)
    pnl = pd.to_numeric(group["pnl"], errors="coerce").fillna(0.0)
    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = float(abs(pnl[pnl < 0].sum()))

    return {
        "pattern_type": pattern_type,
        "pattern_value": pattern_value,
        "total_trades": metrics_dict["total_trades"],
        "wins": metrics_dict["wins"],
        "losses": metrics_dict["losses"],
        "win_rate": metrics_dict["win_rate"],
        "profit_factor": metrics_dict["profit_factor"],
        "net_profit": metrics_dict["net_profit"],
        "max_drawdown_estimated": metrics_dict["max_drawdown"],
        "average_trade": metrics_dict["expectancy"],
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "loss_share": gross_loss / total_gross_loss if total_gross_loss > 0 else 0.0,
    }


def _coverage_row(trades: pd.DataFrame, market_data: pd.DataFrame | None) -> dict:
    if trades.empty:
        return {}
    breakdown = build_daily_breakdown(
        trades,
        strategy_names=(FINAL_BALANCED_STRATEGY_NAME,),
        market_data=market_data,
    )
    coverage = build_daily_coverage_report(breakdown)
    if coverage.empty:
        return {}
    return coverage.iloc[0].to_dict()


def _pattern_mask(trades: pd.DataFrame, pattern_type: str, pattern_value: str) -> pd.Series:
    column_map = {
        "hour": "hour",
        "weekday": "weekday",
        "month": "month",
        "session": "session",
        "side": "side_label",
        "session_side": "session_side",
        "score_bucket": "score_bucket",
        "bars_in_trade_bucket": "bars_in_trade_bucket",
        "signal_reason": "signal_reason_bucket",
    }
    column = column_map.get(pattern_type)
    if column is None or column not in trades.columns:
        return pd.Series(False, index=trades.index)
    return trades[column].astype(str) == str(pattern_value)


def _side_score(trades: pd.DataFrame) -> pd.Series:
    score_long = pd.to_numeric(trades.get("score_long", pd.Series(index=trades.index)), errors="coerce")
    score_short = pd.to_numeric(trades.get("score_short", pd.Series(index=trades.index)), errors="coerce")
    side = trades.get("side", pd.Series(index=trades.index, dtype="object")).astype(str)
    score = score_long.where(side == "BUY", score_short.where(side == "SELL", score_long.combine_first(score_short)))
    return score


def _mode_value(series: pd.Series | None) -> str:
    if series is None or series.empty:
        return "Unknown"
    mode = series.dropna().astype(str).mode()
    return mode.iloc[0] if not mode.empty else "Unknown"


def _mean_optional(series: pd.Series | None) -> float:
    if series is None:
        return float("nan")
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if len(values) else float("nan")


def _column_or_default(df: pd.DataFrame, column: str, default: object) -> pd.Series:
    if column not in df.columns:
        return pd.Series([default if default is not None else "Unknown"] * len(df), index=df.index, dtype="object")
    return df[column].astype("object").where(df[column].notna(), default if default is not None else "Unknown")
