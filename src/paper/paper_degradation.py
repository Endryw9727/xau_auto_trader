"""
Recent degradation diagnostics for controlled paper trading.

These helpers analyze already exported paper reports. They do not alter strategy
logic, generate signals, or execute trades.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.paper.paper_monitor import (
    DEFAULT_MONITOR_STRATEGY_NAME,
    DEFAULT_PAPER_MONITOR_SUMMARY_PATH,
    PaperReports,
    build_monitor_summary,
    current_consecutive_losses,
    max_consecutive_losses,
    profit_factor,
    win_rate,
)


HIGH_MARGIN_STRATEGY_NAME = "proxy_hardened_no_worst_hours_high_margin"
DEFAULT_RECENT_DEGRADATION_PATH = Path("reports/paper/recent_paper_degradation.csv")
DEFAULT_RECENT_DEGRADATION_BREAKDOWN_PATH = Path("reports/paper/recent_paper_degradation_breakdown.csv")
DEFAULT_ROLLING_STABILITY_PATH = Path("reports/paper/rolling_paper_stability.csv")
DEFAULT_WORST_ROLLING_WINDOWS_PATH = Path("reports/paper/worst_rolling_windows.csv")
DEFAULT_MAIN_VS_HIGH_MARGIN_RECENT_PATH = Path("reports/paper/main_vs_high_margin_recent.csv")
DEFAULT_DEFENSIVE_MODE_PATH = Path("reports/paper/defensive_paper_mode.csv")

WINDOW_DEFINITIONS = (
    ("last_30_trades", "trades", 30),
    ("last_50_trades", "trades", 50),
    ("last_100_trades", "trades", 100),
    ("last_month", "months", 1),
    ("last_3_months", "months", 3),
    ("last_6_months", "months", 6),
    ("last_year", "years", 1),
)
ROLLING_WINDOWS = (30, 50, 100)
BREAKDOWN_COLUMNS = (
    "session",
    "hour",
    "side",
    "signal_reason",
    "score_bucket",
    "day_of_week",
    "volatility_regime",
    "trend_regime",
    "candle_regime",
    "regime",
    "mode",
)

DEGRADATION_COLUMNS = [
    "strategy_name",
    "window_label",
    "window_type",
    "window_value",
    "start_time",
    "end_time",
    "total_trades",
    "wins",
    "losses",
    "win_rate",
    "profit_factor",
    "net_profit",
    "average_trade",
    "max_drawdown",
    "max_consecutive_losses",
    "worst_session",
    "worst_hour",
    "worst_side",
    "worst_signal_reason",
    "worst_score_bucket",
    "worst_day_of_week",
    "worst_regime",
]
BREAKDOWN_REPORT_COLUMNS = [
    "strategy_name",
    "window_label",
    "group_type",
    "group_value",
    "total_trades",
    "wins",
    "losses",
    "win_rate",
    "profit_factor",
    "net_profit",
    "average_trade",
    "max_drawdown",
    "max_consecutive_losses",
]
ROLLING_COLUMNS = [
    "strategy_name",
    "window_size",
    "start_trade_number",
    "end_trade_number",
    "start_time",
    "end_time",
    "total_trades",
    "wins",
    "losses",
    "win_rate",
    "rolling_profit_factor",
    "rolling_net_profit",
    "rolling_max_drawdown",
    "rolling_consecutive_losses",
    "worst_session",
    "worst_hour",
    "worst_side",
    "worst_signal_reason",
    "degradation_flag",
]
WORST_ROLLING_COLUMNS = [
    "strategy_name",
    "window_size",
    "worst_metric",
    "start_trade_number",
    "end_trade_number",
    "start_time",
    "end_time",
    "rolling_profit_factor",
    "rolling_net_profit",
    "rolling_max_drawdown",
    "rolling_consecutive_losses",
    "degradation_start_time",
    "worst_session",
    "worst_hour",
    "worst_side",
    "worst_signal_reason",
]
MAIN_VS_COLUMNS = [
    "strategy_name",
    "profit_factor_total",
    "profit_factor_last_30",
    "profit_factor_last_50",
    "profit_factor_last_year",
    "max_drawdown_pct",
    "max_loss_streak",
    "current_loss_streak",
    "trades_per_day",
    "ending_equity",
    "total_trades",
    "avoids_recent_degradation_vs_main",
    "reduces_loss_streak_vs_main",
]
DEFENSIVE_MODE_COLUMNS = [
    "strategy_name",
    "recommended_mode",
    "recommended_strategy",
    "paper_trade_allowed",
    "reason",
    "profit_factor_last_50",
    "max_drawdown_pct",
    "current_loss_streak",
    "max_loss_streak",
    "allow_live",
]


def build_recent_degradation_reports(
    reports: PaperReports,
    strategy_name: str = DEFAULT_MONITOR_STRATEGY_NAME,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build recent-window summary and breakdown reports for one strategy."""
    trades = prepare_paper_trades(_filter_strategy(reports.trades, strategy_name))
    rows = []
    breakdown_rows = []
    for label, window_type, value in WINDOW_DEFINITIONS:
        window = select_recent_window(trades, window_type, value)
        metrics = metrics_for_trades(window)
        rows.append(
            {
                "strategy_name": strategy_name,
                "window_label": label,
                "window_type": window_type,
                "window_value": value,
                "start_time": _time_value(window, first=True),
                "end_time": _time_value(window, first=False),
                **metrics,
                "worst_session": worst_group_value(window, "session"),
                "worst_hour": worst_group_value(window, "hour"),
                "worst_side": worst_group_value(window, "side"),
                "worst_signal_reason": worst_group_value(window, "signal_reason"),
                "worst_score_bucket": worst_group_value(window, "score_bucket"),
                "worst_day_of_week": worst_group_value(window, "day_of_week"),
                "worst_regime": worst_available_regime(window),
            }
        )
        breakdown_rows.extend(build_breakdown_rows(window, strategy_name, label))
    return (
        pd.DataFrame(rows, columns=DEGRADATION_COLUMNS),
        pd.DataFrame(breakdown_rows, columns=BREAKDOWN_REPORT_COLUMNS),
    )


def build_rolling_stability_reports(
    reports: PaperReports,
    strategy_name: str = DEFAULT_MONITOR_STRATEGY_NAME,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build rolling-window metrics and worst rolling windows."""
    trades = prepare_paper_trades(_filter_strategy(reports.trades, strategy_name))
    rolling_rows = []
    worst_rows = []
    for window_size in ROLLING_WINDOWS:
        rolling = rolling_metrics(trades, window_size, strategy_name)
        if not rolling.empty:
            rolling_rows.append(rolling)
            worst_rows.append(worst_rolling_window_row(rolling, window_size, strategy_name))
    rolling_report = pd.concat(rolling_rows, ignore_index=True) if rolling_rows else pd.DataFrame(columns=ROLLING_COLUMNS)
    worst_report = pd.DataFrame(worst_rows, columns=WORST_ROLLING_COLUMNS)
    return rolling_report, worst_report


def build_main_vs_high_margin_recent_report(
    reports: PaperReports,
    strategy_names: tuple[str, str] = (DEFAULT_MONITOR_STRATEGY_NAME, HIGH_MARGIN_STRATEGY_NAME),
) -> pd.DataFrame:
    """Compare main and high-margin candidates on recent paper windows."""
    rows = []
    metrics_by_name = {}
    for strategy_name in strategy_names:
        trades = prepare_paper_trades(_filter_strategy(reports.trades, strategy_name))
        equity = _filter_strategy(reports.equity_curve, strategy_name)
        daily = _filter_strategy(reports.daily_summary, strategy_name)
        metrics_by_name[strategy_name] = compare_strategy_metrics(trades, equity, daily)

    main = metrics_by_name.get(strategy_names[0], {})
    for strategy_name in strategy_names:
        item = metrics_by_name.get(strategy_name, {})
        rows.append(
            {
                "strategy_name": strategy_name,
                **item,
                "avoids_recent_degradation_vs_main": bool(
                    strategy_name != strategy_names[0]
                    and item.get("profit_factor_last_50", 0.0) > main.get("profit_factor_last_50", 0.0)
                    and item.get("max_drawdown_pct", 0.0) < main.get("max_drawdown_pct", 0.0)
                ),
                "reduces_loss_streak_vs_main": bool(
                    strategy_name != strategy_names[0]
                    and item.get("max_loss_streak", 0) < main.get("max_loss_streak", 0)
                ),
            }
        )
    return pd.DataFrame(rows, columns=MAIN_VS_COLUMNS)


def build_defensive_mode_report(
    monitor_summary: pd.DataFrame,
    strategy_name: str = DEFAULT_MONITOR_STRATEGY_NAME,
    backup_strategy_name: str = HIGH_MARGIN_STRATEGY_NAME,
) -> pd.DataFrame:
    """Return NORMAL/DEFENSIVE/PAUSE recommendation without changing execution."""
    if monitor_summary.empty:
        raise ValueError("monitor_summary must not be empty")
    row = monitor_summary.iloc[0]
    mode, recommended, allowed, reasons = select_defensive_mode(row, backup_strategy_name)
    result = {
        "strategy_name": strategy_name,
        "recommended_mode": mode,
        "recommended_strategy": recommended,
        "paper_trade_allowed": allowed,
        "reason": "; ".join(reasons),
        "profit_factor_last_50": float(row.get("profit_factor_last_50", 0.0)),
        "max_drawdown_pct": float(row.get("max_drawdown_pct", 0.0)),
        "current_loss_streak": int(row.get("current_consecutive_losses", 0)),
        "max_loss_streak": int(row.get("max_consecutive_losses", 0)),
        "allow_live": False,
    }
    return pd.DataFrame([result], columns=DEFENSIVE_MODE_COLUMNS)


def select_defensive_mode(row: pd.Series, backup_strategy_name: str = HIGH_MARGIN_STRATEGY_NAME) -> tuple[str, str, bool, list[str]]:
    """Select NORMAL, DEFENSIVE, or PAUSE from monitor metrics."""
    pf_50 = float(row.get("profit_factor_last_50", 0.0))
    dd = float(row.get("max_drawdown_pct", 0.0))
    current_losses = int(row.get("current_consecutive_losses", 0))

    pause_reasons = []
    if pf_50 < 1.00:
        pause_reasons.append(f"PF ultime 50 {pf_50:.2f} < 1.00")
    if dd > 12.0:
        pause_reasons.append(f"DD {dd:.2f}% > 12%")
    if current_losses > 10:
        pause_reasons.append(f"loss streak attuale {current_losses} > 10")
    if pause_reasons:
        return "PAUSE", "none", False, pause_reasons

    defensive_reasons = []
    if 1.00 <= pf_50 < 1.10:
        defensive_reasons.append(f"PF ultime 50 {pf_50:.2f} tra 1.00 e 1.10")
    if 8.0 <= dd <= 12.0:
        defensive_reasons.append(f"DD {dd:.2f}% tra 8% e 12%")
    if 5 <= current_losses <= 10:
        defensive_reasons.append(f"loss streak attuale {current_losses} tra 5 e 10")
    if defensive_reasons:
        return "DEFENSIVE", backup_strategy_name, True, defensive_reasons

    return "NORMAL", str(row.get("strategy_name", DEFAULT_MONITOR_STRATEGY_NAME)), True, [
        "PF ultime 50 >= 1.10, DD < 8%, loss streak attuale < 5"
    ]


def prepare_paper_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Normalize paper trade fields and add derived grouping columns."""
    result = trades.copy()
    if result.empty:
        return result
    result["entry_time"] = pd.to_datetime(result["entry_time"], errors="coerce")
    result = result.dropna(subset=["entry_time"]).sort_values("entry_time").reset_index(drop=True)
    result["pnl_eur"] = _numeric_column(result, "pnl_eur")
    result["hour"] = result["entry_time"].dt.hour
    result["day_of_week"] = result["entry_time"].dt.day_name()
    result["session"] = _string_column(result, "session", "UNKNOWN").str.upper()
    result["side"] = _string_column(result, "side", "UNKNOWN").str.upper()
    result["signal_reason"] = _string_column(result, "signal_reason", "UNKNOWN")
    score = pd.to_numeric(result["score"], errors="coerce") if "score" in result.columns else pd.Series([pd.NA] * len(result), index=result.index)
    if score.isna().all():
        side = result["side"]
        long_score = _numeric_column(result, "score_long")
        short_score = _numeric_column(result, "score_short")
        score = long_score.where(side == "BUY", short_score)
    result["score"] = score.fillna(0.0)
    result["score_bucket"] = pd.cut(
        result["score"],
        bins=[-float("inf"), 69.999, 74.999, 79.999, 89.999, float("inf")],
        labels=["score_lt_70", "score_70_74", "score_75_79", "score_80_89", "score_90_plus"],
    ).astype("string")
    return result


def select_recent_window(trades: pd.DataFrame, window_type: str, value: int) -> pd.DataFrame:
    """Select recent trades by count or calendar offset."""
    if trades.empty:
        return trades.copy()
    if window_type == "trades":
        return trades.tail(value).copy()
    end_time = trades["entry_time"].max()
    if window_type == "months":
        start_time = end_time - pd.DateOffset(months=value)
    elif window_type == "years":
        start_time = end_time - pd.DateOffset(years=value)
    else:
        raise ValueError(f"Unsupported window_type: {window_type}")
    return trades[trades["entry_time"] >= start_time].copy()


def metrics_for_trades(trades: pd.DataFrame) -> dict:
    """Calculate core trade metrics for a trade slice."""
    if trades.empty:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "net_profit": 0.0,
            "average_trade": 0.0,
            "max_drawdown": 0.0,
            "max_consecutive_losses": 0,
        }
    pnl = pd.to_numeric(trades["pnl_eur"], errors="coerce").fillna(0.0)
    return {
        "total_trades": int(len(trades)),
        "wins": int((pnl > 0).sum()),
        "losses": int((pnl < 0).sum()),
        "win_rate": win_rate(pnl),
        "profit_factor": profit_factor(pnl),
        "net_profit": float(pnl.sum()),
        "average_trade": float(pnl.mean()),
        "max_drawdown": pnl_drawdown(pnl),
        "max_consecutive_losses": max_consecutive_losses(pnl),
    }


def build_breakdown_rows(trades: pd.DataFrame, strategy_name: str, window_label: str) -> list[dict]:
    """Build group breakdown rows for available columns."""
    rows = []
    for column in BREAKDOWN_COLUMNS:
        if column not in trades.columns:
            continue
        for value, group in trades.groupby(column, dropna=False):
            rows.append(
                {
                    "strategy_name": strategy_name,
                    "window_label": window_label,
                    "group_type": column,
                    "group_value": str(value),
                    **metrics_for_trades(group),
                }
            )
    return rows


def rolling_metrics(trades: pd.DataFrame, window_size: int, strategy_name: str) -> pd.DataFrame:
    """Build rolling trade-window metrics."""
    if len(trades) < window_size:
        return pd.DataFrame(columns=ROLLING_COLUMNS)
    rows = []
    for end_index in range(window_size, len(trades) + 1):
        start_index = end_index - window_size
        window = trades.iloc[start_index:end_index].copy()
        metrics = metrics_for_trades(window)
        rows.append(
            {
                "strategy_name": strategy_name,
                "window_size": window_size,
                "start_trade_number": start_index + 1,
                "end_trade_number": end_index,
                "start_time": _time_value(window, first=True),
                "end_time": _time_value(window, first=False),
                "total_trades": metrics["total_trades"],
                "wins": metrics["wins"],
                "losses": metrics["losses"],
                "win_rate": metrics["win_rate"],
                "rolling_profit_factor": metrics["profit_factor"],
                "rolling_net_profit": metrics["net_profit"],
                "rolling_max_drawdown": metrics["max_drawdown"],
                "rolling_consecutive_losses": metrics["max_consecutive_losses"],
                "worst_session": worst_group_value(window, "session"),
                "worst_hour": worst_group_value(window, "hour"),
                "worst_side": worst_group_value(window, "side"),
                "worst_signal_reason": worst_group_value(window, "signal_reason"),
                "degradation_flag": bool(metrics["profit_factor"] < 1.10),
            }
        )
    return pd.DataFrame(rows, columns=ROLLING_COLUMNS)


def worst_rolling_window_row(rolling: pd.DataFrame, window_size: int, strategy_name: str) -> dict:
    """Return the worst rolling row by PF then net profit."""
    sorted_rows = rolling.sort_values(["rolling_profit_factor", "rolling_net_profit"], ascending=[True, True])
    worst = sorted_rows.iloc[0]
    degradation = rolling[rolling["degradation_flag"]].sort_values("start_trade_number")
    degradation_start = degradation.iloc[0]["start_time"] if not degradation.empty else ""
    return {
        "strategy_name": strategy_name,
        "window_size": window_size,
        "worst_metric": "rolling_profit_factor",
        "start_trade_number": int(worst["start_trade_number"]),
        "end_trade_number": int(worst["end_trade_number"]),
        "start_time": worst["start_time"],
        "end_time": worst["end_time"],
        "rolling_profit_factor": float(worst["rolling_profit_factor"]),
        "rolling_net_profit": float(worst["rolling_net_profit"]),
        "rolling_max_drawdown": float(worst["rolling_max_drawdown"]),
        "rolling_consecutive_losses": int(worst["rolling_consecutive_losses"]),
        "degradation_start_time": degradation_start,
        "worst_session": worst["worst_session"],
        "worst_hour": worst["worst_hour"],
        "worst_side": worst["worst_side"],
        "worst_signal_reason": worst["worst_signal_reason"],
    }


def compare_strategy_metrics(trades: pd.DataFrame, equity: pd.DataFrame, daily: pd.DataFrame) -> dict:
    """Calculate comparison metrics for one paper strategy."""
    pnl = pd.to_numeric(trades.get("pnl_eur", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    last_year = select_recent_window(trades, "years", 1)
    daily = daily.copy()
    if not daily.empty:
        daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    trading_days = int(len(daily)) if not daily.empty else max(1, trades["entry_time"].dt.date.nunique()) if not trades.empty else 0
    return {
        "profit_factor_total": profit_factor(pnl),
        "profit_factor_last_30": profit_factor(pnl.tail(30)),
        "profit_factor_last_50": profit_factor(pnl.tail(50)),
        "profit_factor_last_year": profit_factor(pd.to_numeric(last_year.get("pnl_eur", pd.Series(dtype=float)), errors="coerce").fillna(0.0)),
        "max_drawdown_pct": _max_numeric(equity, "drawdown_percent"),
        "max_loss_streak": max_consecutive_losses(pnl),
        "current_loss_streak": current_consecutive_losses(pnl),
        "trades_per_day": len(trades) / trading_days if trading_days else 0.0,
        "ending_equity": _last_numeric(equity, "equity_after"),
        "total_trades": int(len(trades)),
    }


def worst_group_value(trades: pd.DataFrame, column: str) -> str:
    """Return the worst group label by net profit for a column."""
    if trades.empty or column not in trades.columns:
        return ""
    grouped = trades.groupby(column, dropna=False)["pnl_eur"].sum().sort_values()
    if grouped.empty:
        return ""
    value = grouped.index[0]
    return str(value)


def worst_available_regime(trades: pd.DataFrame) -> str:
    """Return worst optional regime/mode value if present."""
    for column in ("volatility_regime", "trend_regime", "candle_regime", "regime", "mode"):
        value = worst_group_value(trades, column)
        if value:
            return f"{column}:{value}"
    return ""


def pnl_drawdown(pnl: pd.Series) -> float:
    """Return maximum drawdown of a P&L path starting from zero."""
    pnl = pd.to_numeric(pnl, errors="coerce").fillna(0.0)
    if pnl.empty:
        return 0.0
    cumulative = pnl.cumsum()
    running_high = cumulative.cummax().clip(lower=0.0)
    drawdown = running_high - cumulative
    return float(drawdown.max())


def export_dataframe(df: pd.DataFrame, path: str | Path) -> Path:
    """Export report CSV."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path


def load_or_build_monitor_summary(reports: PaperReports) -> pd.DataFrame:
    """Load monitor summary when present, otherwise calculate it."""
    if DEFAULT_PAPER_MONITOR_SUMMARY_PATH.exists():
        return pd.read_csv(DEFAULT_PAPER_MONITOR_SUMMARY_PATH)
    return build_monitor_summary(reports, strategy_name=DEFAULT_MONITOR_STRATEGY_NAME)


def _filter_strategy(df: pd.DataFrame, strategy_name: str) -> pd.DataFrame:
    if df.empty or "strategy_name" not in df.columns:
        return df.copy()
    return df[df["strategy_name"] == strategy_name].copy()


def _string_column(df: pd.DataFrame, column: str, default: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series([default] * len(df), index=df.index, dtype="string")
    return df[column].fillna(default).astype("string")


def _numeric_column(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series([0.0] * len(df), index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def _time_value(trades: pd.DataFrame, first: bool) -> str:
    if trades.empty:
        return ""
    value = trades["entry_time"].iloc[0 if first else -1]
    return str(value)


def _last_numeric(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    return float(values.iloc[-1]) if not values.empty else 0.0


def _max_numeric(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    return float(values.max()) if not values.empty else 0.0
