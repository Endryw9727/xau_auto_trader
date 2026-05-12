"""
Paper monitoring and validation helpers.

The monitor reads local paper CSV reports and calculates operational status.
It does not generate signals, change strategy logic, or execute orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from src.paper.paper_engine import (
    DEFAULT_PAPER_DAILY_SUMMARY_PATH,
    DEFAULT_PAPER_EQUITY_CURVE_PATH,
    DEFAULT_PAPER_TRADES_PATH,
)


DEFAULT_PAPER_MONITOR_SUMMARY_PATH = Path("reports/paper/paper_monitor_summary.csv")
DEFAULT_PAPER_VALIDATION_STATUS_PATH = Path("reports/paper/paper_validation_status.csv")
DEFAULT_PAPER_VALIDATION_RULES_PATH = Path("config/paper_validation_rules.yaml")
DEFAULT_MONITOR_STRATEGY_NAME = "proxy_hardened_no_worst_hours"

MONITOR_SUMMARY_COLUMNS = [
    "strategy_name",
    "report_as_of",
    "status",
    "warning_reasons",
    "stop_reasons",
    "equity_current",
    "total_profit_loss",
    "current_drawdown_eur",
    "current_drawdown_pct",
    "max_drawdown_eur",
    "max_drawdown_pct",
    "total_trades",
    "trades_today",
    "trades_week",
    "trades_month",
    "profit_factor_total",
    "profit_factor_last_30",
    "profit_factor_last_50",
    "win_rate_total",
    "win_rate_last_30",
    "max_consecutive_losses",
    "current_consecutive_losses",
    "daily_loss_current",
    "daily_loss_current_pct",
    "weekly_loss_current",
    "weekly_loss_current_pct",
    "total_no_trade_days",
    "current_no_trade_days",
    "last_trade_time",
    "last_entry_reason",
    "last_session",
    "last_result",
]

VALIDATION_STATUS_COLUMNS = [
    "strategy_name",
    "validation_status",
    "allow_live",
    "ready_for_demo",
    "ready_for_micro_live",
    "paper_days",
    "total_trades",
    "profit_factor_total",
    "profit_factor_last_50",
    "max_drawdown_pct",
    "max_consecutive_losses",
    "max_trades_per_day_observed",
    "fail_reasons",
    "observation_reasons",
]


@dataclass(frozen=True)
class PaperValidationRules:
    """Validation thresholds for controlled paper monitoring."""

    min_paper_trades_before_live: int
    ideal_paper_trades_before_live: int
    min_days_before_live: int
    max_allowed_drawdown_pct: float
    warning_drawdown_pct: float
    min_total_pf: float
    min_recent_50_pf: float
    max_consecutive_losses: int
    max_daily_loss_pct: float
    max_weekly_loss_pct: float
    max_trades_per_day: int
    allow_live: bool


@dataclass(frozen=True)
class PaperReports:
    """Loaded paper report frames."""

    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    daily_summary: pd.DataFrame


def load_validation_rules(path: str | Path = DEFAULT_PAPER_VALIDATION_RULES_PATH) -> PaperValidationRules:
    """Load validation thresholds and keep live permission disabled."""
    rules_path = Path(path)
    if not rules_path.exists():
        raise FileNotFoundError(f"Paper validation rules not found: {rules_path}")
    with rules_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)
    if not isinstance(raw, dict):
        raise ValueError("paper_validation_rules.yaml must contain a YAML dictionary")
    rules = PaperValidationRules(
        min_paper_trades_before_live=int(raw.get("min_paper_trades_before_live", 60)),
        ideal_paper_trades_before_live=int(raw.get("ideal_paper_trades_before_live", 100)),
        min_days_before_live=int(raw.get("min_days_before_live", 30)),
        max_allowed_drawdown_pct=float(raw.get("max_allowed_drawdown_pct", 12.0)),
        warning_drawdown_pct=float(raw.get("warning_drawdown_pct", 8.0)),
        min_total_pf=float(raw.get("min_total_pf", 1.20)),
        min_recent_50_pf=float(raw.get("min_recent_50_pf", 1.05)),
        max_consecutive_losses=int(raw.get("max_consecutive_losses", 8)),
        max_daily_loss_pct=float(raw.get("max_daily_loss_pct", 3.0)),
        max_weekly_loss_pct=float(raw.get("max_weekly_loss_pct", 8.0)),
        max_trades_per_day=int(raw.get("max_trades_per_day", 2)),
        allow_live=False,
    )
    return rules


def load_paper_reports(
    trades_path: str | Path = DEFAULT_PAPER_TRADES_PATH,
    equity_curve_path: str | Path = DEFAULT_PAPER_EQUITY_CURVE_PATH,
    daily_summary_path: str | Path = DEFAULT_PAPER_DAILY_SUMMARY_PATH,
) -> PaperReports:
    """Load local paper reports from CSV files."""
    paths = [Path(trades_path), Path(equity_curve_path), Path(daily_summary_path)]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing paper report(s): " + ", ".join(missing))
    return PaperReports(
        trades=pd.read_csv(paths[0]),
        equity_curve=pd.read_csv(paths[1]),
        daily_summary=pd.read_csv(paths[2]),
    )


def build_monitor_summary(
    reports: PaperReports,
    strategy_name: str = DEFAULT_MONITOR_STRATEGY_NAME,
) -> pd.DataFrame:
    """Build one-row monitor summary for a paper strategy."""
    trades = _filter_strategy(reports.trades, strategy_name)
    equity = _filter_strategy(reports.equity_curve, strategy_name)
    daily = _filter_strategy(reports.daily_summary, strategy_name)
    row = calculate_monitor_metrics(trades, equity, daily, strategy_name)
    status, warnings, stops = evaluate_daily_status(row)
    row["status"] = status
    row["warning_reasons"] = "; ".join(warnings)
    row["stop_reasons"] = "; ".join(stops)
    return pd.DataFrame([row], columns=MONITOR_SUMMARY_COLUMNS)


def calculate_monitor_metrics(
    trades: pd.DataFrame,
    equity_curve: pd.DataFrame,
    daily_summary: pd.DataFrame,
    strategy_name: str,
) -> dict:
    """Calculate operational paper metrics from local CSV rows."""
    trades = _prepare_trades(trades)
    equity_curve = _prepare_equity(equity_curve)
    daily_summary = _prepare_daily(daily_summary)

    as_of = _report_as_of(trades, daily_summary)
    pnl = pd.to_numeric(trades.get("pnl_eur", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    last_30 = pnl.tail(30)
    last_50 = pnl.tail(50)
    daily_current = _current_day_pnl(daily_summary, as_of)
    weekly_current = _current_week_pnl(daily_summary, as_of)
    current_equity = _last_numeric(equity_curve, "equity_after", default=0.0)
    start_equity = _first_numeric(equity_curve, "equity_before", default=current_equity)
    last_trade = trades.iloc[-1] if not trades.empty else pd.Series(dtype=object)

    current_drawdown_eur = _last_numeric(equity_curve, "drawdown_eur", default=0.0)
    current_drawdown_pct = _last_numeric(equity_curve, "drawdown_percent", default=0.0)
    max_drawdown_eur = _max_numeric(equity_curve, "drawdown_eur")
    max_drawdown_pct = _max_numeric(equity_curve, "drawdown_percent")
    total_no_trade_days = int((pd.to_numeric(daily_summary.get("trades", pd.Series(dtype=float)), errors="coerce").fillna(0) == 0).sum())

    return {
        "strategy_name": strategy_name,
        "report_as_of": as_of.date().isoformat() if pd.notna(as_of) else "",
        "status": "OK",
        "warning_reasons": "",
        "stop_reasons": "",
        "equity_current": current_equity,
        "total_profit_loss": current_equity - start_equity,
        "current_drawdown_eur": current_drawdown_eur,
        "current_drawdown_pct": current_drawdown_pct,
        "max_drawdown_eur": max_drawdown_eur,
        "max_drawdown_pct": max_drawdown_pct,
        "total_trades": int(len(trades)),
        "trades_today": _trades_in_current_day(trades, as_of),
        "trades_week": _trades_in_current_week(trades, as_of),
        "trades_month": _trades_in_current_month(trades, as_of),
        "profit_factor_total": profit_factor(pnl),
        "profit_factor_last_30": profit_factor(last_30),
        "profit_factor_last_50": profit_factor(last_50),
        "win_rate_total": win_rate(pnl),
        "win_rate_last_30": win_rate(last_30),
        "max_consecutive_losses": max_consecutive_losses(pnl),
        "current_consecutive_losses": current_consecutive_losses(pnl),
        "daily_loss_current": min(0.0, daily_current),
        "daily_loss_current_pct": loss_pct_for_period(daily_summary, as_of, "D"),
        "weekly_loss_current": min(0.0, weekly_current),
        "weekly_loss_current_pct": loss_pct_for_period(daily_summary, as_of, "W"),
        "total_no_trade_days": total_no_trade_days,
        "current_no_trade_days": current_no_trade_days(daily_summary),
        "last_trade_time": str(last_trade.get("entry_time", "")) if not last_trade.empty else "",
        "last_entry_reason": str(last_trade.get("signal_reason", "")) if not last_trade.empty else "",
        "last_session": str(last_trade.get("session", "")) if not last_trade.empty else "",
        "last_result": result_label(last_trade.get("pnl_eur", 0.0)) if not last_trade.empty else "",
    }


def evaluate_daily_status(row: dict | pd.Series) -> tuple[str, list[str], list[str]]:
    """Return OK/WARNING/STOP status and reasons for daily monitoring."""
    data = dict(row)
    effective_dd = max(float(data.get("current_drawdown_pct", 0.0)), float(data.get("max_drawdown_pct", 0.0)))
    warnings = []
    stops = []

    if effective_dd > 12.0:
        stops.append(f"drawdown {effective_dd:.2f}% > 12%")
    if int(data.get("current_consecutive_losses", 0)) >= 8:
        stops.append("8 loss consecutive")
    if float(data.get("daily_loss_current_pct", 0.0)) > 3.0:
        stops.append(f"perdita giornaliera {float(data['daily_loss_current_pct']):.2f}% > 3%")
    if float(data.get("weekly_loss_current_pct", 0.0)) > 8.0:
        stops.append(f"perdita settimanale {float(data['weekly_loss_current_pct']):.2f}% > 8%")
    pf_50 = float(data.get("profit_factor_last_50", 0.0))
    if int(data.get("total_trades", 0)) >= 50 and pf_50 < 1.00:
        stops.append(f"PF ultime 50 operazioni {pf_50:.2f} < 1.00")

    if effective_dd > 8.0:
        warnings.append(f"drawdown {effective_dd:.2f}% > 8%")
    pf_30 = float(data.get("profit_factor_last_30", 0.0))
    if int(data.get("total_trades", 0)) >= 30 and pf_30 < 1.10:
        warnings.append(f"PF ultime 30 operazioni {pf_30:.2f} < 1.10")
    if int(data.get("current_consecutive_losses", 0)) >= 5:
        warnings.append("5 loss consecutive")
    if float(data.get("weekly_loss_current_pct", 0.0)) > 5.0:
        warnings.append(f"perdita settimanale {float(data['weekly_loss_current_pct']):.2f}% > 5%")

    if stops:
        return "STOP", warnings, stops
    if warnings:
        return "WARNING", warnings, []
    return "OK", [], []


def build_validation_status(
    monitor_summary: pd.DataFrame,
    daily_summary: pd.DataFrame,
    rules: PaperValidationRules,
    strategy_name: str = DEFAULT_MONITOR_STRATEGY_NAME,
) -> pd.DataFrame:
    """Build one-row validation status for controlled paper gates."""
    if monitor_summary.empty:
        raise ValueError("monitor_summary must not be empty")
    row = monitor_summary.iloc[0]
    daily = _filter_strategy(_prepare_daily(daily_summary), strategy_name)
    paper_days = int(len(daily))
    max_trades_observed = int(pd.to_numeric(daily.get("trades", pd.Series(dtype=float)), errors="coerce").fillna(0).max()) if not daily.empty else 0
    fail_reasons, observation_reasons = validation_reasons(row, paper_days, max_trades_observed, rules)
    ready_for_demo = not fail_reasons and not observation_reasons
    ready_for_micro_live = bool(ready_for_demo and rules.allow_live)
    if fail_reasons:
        status = "non pronto"
    elif observation_reasons:
        status = "in osservazione"
    elif ready_for_micro_live:
        status = "pronto per micro-live"
    else:
        status = "pronto per demo"

    result = {
        "strategy_name": strategy_name,
        "validation_status": status,
        "allow_live": False,
        "ready_for_demo": bool(ready_for_demo),
        "ready_for_micro_live": False,
        "paper_days": paper_days,
        "total_trades": int(row.get("total_trades", 0)),
        "profit_factor_total": float(row.get("profit_factor_total", 0.0)),
        "profit_factor_last_50": float(row.get("profit_factor_last_50", 0.0)),
        "max_drawdown_pct": float(row.get("max_drawdown_pct", 0.0)),
        "max_consecutive_losses": int(row.get("max_consecutive_losses", 0)),
        "max_trades_per_day_observed": max_trades_observed,
        "fail_reasons": "; ".join(fail_reasons),
        "observation_reasons": "; ".join(observation_reasons),
    }
    return pd.DataFrame([result], columns=VALIDATION_STATUS_COLUMNS)


def validation_reasons(
    row: pd.Series,
    paper_days: int,
    max_trades_observed: int,
    rules: PaperValidationRules,
) -> tuple[list[str], list[str]]:
    """Return hard failures and observation reasons for paper validation."""
    fail_reasons = []
    observation_reasons = []
    total_trades = int(row.get("total_trades", 0))
    total_pf = float(row.get("profit_factor_total", 0.0))
    recent_pf = float(row.get("profit_factor_last_50", 0.0))
    max_dd = float(row.get("max_drawdown_pct", 0.0))
    max_losses = int(row.get("max_consecutive_losses", 0))
    daily_loss = float(row.get("daily_loss_current_pct", 0.0))
    weekly_loss = float(row.get("weekly_loss_current_pct", 0.0))

    if total_trades < rules.min_paper_trades_before_live:
        fail_reasons.append(f"trade paper {total_trades} < minimo {rules.min_paper_trades_before_live}")
    if paper_days < rules.min_days_before_live:
        fail_reasons.append(f"giorni paper {paper_days} < minimo {rules.min_days_before_live}")
    if total_pf < rules.min_total_pf:
        fail_reasons.append(f"PF totale {total_pf:.2f} < {rules.min_total_pf:.2f}")
    if total_trades >= 50 and recent_pf < rules.min_recent_50_pf:
        fail_reasons.append(f"PF ultime 50 {recent_pf:.2f} < {rules.min_recent_50_pf:.2f}")
    if max_dd > rules.max_allowed_drawdown_pct:
        fail_reasons.append(f"drawdown massimo {max_dd:.2f}% > {rules.max_allowed_drawdown_pct:.2f}%")
    if daily_loss > rules.max_daily_loss_pct:
        fail_reasons.append(f"perdita giornaliera {daily_loss:.2f}% > {rules.max_daily_loss_pct:.2f}%")
    if weekly_loss > rules.max_weekly_loss_pct:
        fail_reasons.append(f"perdita settimanale {weekly_loss:.2f}% > {rules.max_weekly_loss_pct:.2f}%")
    if max_trades_observed > rules.max_trades_per_day:
        fail_reasons.append(f"trade/giorno osservati {max_trades_observed} > {rules.max_trades_per_day}")

    if total_trades < rules.ideal_paper_trades_before_live:
        observation_reasons.append(f"trade paper {total_trades} < ideale {rules.ideal_paper_trades_before_live}")
    if max_dd > rules.warning_drawdown_pct:
        observation_reasons.append(f"drawdown massimo {max_dd:.2f}% > warning {rules.warning_drawdown_pct:.2f}%")
    if max_losses > rules.max_consecutive_losses:
        observation_reasons.append(f"max loss consecutive {max_losses} > {rules.max_consecutive_losses}")
    if not rules.allow_live:
        observation_reasons.append("allow_live=false: nessuna attivazione automatica")
    return fail_reasons, observation_reasons


def export_monitor_summary(summary: pd.DataFrame, path: str | Path = DEFAULT_PAPER_MONITOR_SUMMARY_PATH) -> Path:
    """Export monitor summary CSV."""
    return _export(summary, path)


def export_validation_status(status: pd.DataFrame, path: str | Path = DEFAULT_PAPER_VALIDATION_STATUS_PATH) -> Path:
    """Export validation status CSV."""
    return _export(status, path)


def profit_factor(pnl: pd.Series) -> float:
    """Calculate profit factor from P&L."""
    pnl = pd.to_numeric(pnl, errors="coerce").fillna(0.0)
    if pnl.empty:
        return 0.0
    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = float(abs(pnl[pnl < 0].sum()))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def win_rate(pnl: pd.Series) -> float:
    """Calculate win rate percentage."""
    pnl = pd.to_numeric(pnl, errors="coerce").fillna(0.0)
    return float((pnl > 0).sum() / len(pnl) * 100) if len(pnl) else 0.0


def max_consecutive_losses(pnl: pd.Series) -> int:
    """Calculate maximum consecutive losing trades."""
    longest = current = 0
    for value in pd.to_numeric(pnl, errors="coerce").fillna(0.0):
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def current_consecutive_losses(pnl: pd.Series) -> int:
    """Calculate current trailing losing streak."""
    current = 0
    for value in reversed(list(pd.to_numeric(pnl, errors="coerce").fillna(0.0))):
        if value < 0:
            current += 1
        else:
            break
    return int(current)


def current_no_trade_days(daily_summary: pd.DataFrame) -> int:
    """Return trailing days with zero trades."""
    if daily_summary.empty:
        return 0
    current = 0
    trades = pd.to_numeric(daily_summary["trades"], errors="coerce").fillna(0)
    for value in reversed(list(trades)):
        if int(value) == 0:
            current += 1
        else:
            break
    return int(current)


def result_label(value: object) -> str:
    """Return WIN/LOSS/BREAK_EVEN for a trade P&L value."""
    pnl = pd.to_numeric(value, errors="coerce")
    if pd.isna(pnl) or float(pnl) == 0:
        return "BREAK_EVEN"
    return "WIN" if float(pnl) > 0 else "LOSS"


def loss_pct_for_period(daily_summary: pd.DataFrame, as_of: pd.Timestamp, freq: str) -> float:
    """Return current period loss percentage using period start equity."""
    if daily_summary.empty or pd.isna(as_of):
        return 0.0
    prepared = daily_summary.copy()
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared = prepared.dropna(subset=["date"])
    if freq == "D":
        group = prepared[prepared["date"].dt.normalize() == as_of.normalize()]
    else:
        period = as_of.to_period(freq)
        group = prepared[prepared["date"].dt.to_period(freq) == period]
    if group.empty:
        return 0.0
    pnl = pd.to_numeric(group["net_profit"], errors="coerce").fillna(0.0)
    total_pnl = float(pnl.sum())
    if total_pnl >= 0:
        return 0.0
    first = group.iloc[0]
    start_equity = float(pd.to_numeric(first["ending_equity"], errors="coerce") - pd.to_numeric(first["net_profit"], errors="coerce"))
    if start_equity <= 0:
        return 0.0
    return abs(total_pnl) / start_equity * 100


def _filter_strategy(df: pd.DataFrame, strategy_name: str) -> pd.DataFrame:
    if df.empty or "strategy_name" not in df.columns:
        return df.copy()
    return df[df["strategy_name"] == strategy_name].copy()


def _prepare_trades(trades: pd.DataFrame) -> pd.DataFrame:
    result = trades.copy()
    if result.empty:
        return result
    result["entry_time"] = pd.to_datetime(result["entry_time"], errors="coerce")
    result = result.dropna(subset=["entry_time"]).sort_values("entry_time").reset_index(drop=True)
    return result


def _prepare_equity(equity: pd.DataFrame) -> pd.DataFrame:
    result = equity.copy()
    if result.empty:
        return result
    result["entry_time"] = pd.to_datetime(result["entry_time"], errors="coerce")
    return result.dropna(subset=["entry_time"]).sort_values("entry_time").reset_index(drop=True)


def _prepare_daily(daily: pd.DataFrame) -> pd.DataFrame:
    result = daily.copy()
    if result.empty:
        return result
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    return result.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def _report_as_of(trades: pd.DataFrame, daily_summary: pd.DataFrame) -> pd.Timestamp:
    candidates = []
    if not trades.empty:
        candidates.append(pd.to_datetime(trades["entry_time"], errors="coerce").max())
    if not daily_summary.empty:
        candidates.append(pd.to_datetime(daily_summary["date"], errors="coerce").max())
    candidates = [candidate for candidate in candidates if pd.notna(candidate)]
    return max(candidates) if candidates else pd.NaT


def _current_day_pnl(daily_summary: pd.DataFrame, as_of: pd.Timestamp) -> float:
    if daily_summary.empty or pd.isna(as_of):
        return 0.0
    day = daily_summary[daily_summary["date"].dt.normalize() == as_of.normalize()]
    return float(pd.to_numeric(day.get("net_profit", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())


def _current_week_pnl(daily_summary: pd.DataFrame, as_of: pd.Timestamp) -> float:
    if daily_summary.empty or pd.isna(as_of):
        return 0.0
    period = as_of.to_period("W")
    week = daily_summary[daily_summary["date"].dt.to_period("W") == period]
    return float(pd.to_numeric(week.get("net_profit", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())


def _trades_in_current_day(trades: pd.DataFrame, as_of: pd.Timestamp) -> int:
    if trades.empty or pd.isna(as_of):
        return 0
    return int((trades["entry_time"].dt.normalize() == as_of.normalize()).sum())


def _trades_in_current_week(trades: pd.DataFrame, as_of: pd.Timestamp) -> int:
    if trades.empty or pd.isna(as_of):
        return 0
    return int((trades["entry_time"].dt.to_period("W") == as_of.to_period("W")).sum())


def _trades_in_current_month(trades: pd.DataFrame, as_of: pd.Timestamp) -> int:
    if trades.empty or pd.isna(as_of):
        return 0
    return int((trades["entry_time"].dt.to_period("M") == as_of.to_period("M")).sum())


def _last_numeric(df: pd.DataFrame, column: str, default: float = 0.0) -> float:
    if df.empty or column not in df.columns:
        return default
    series = pd.to_numeric(df[column], errors="coerce").dropna()
    return float(series.iloc[-1]) if not series.empty else default


def _first_numeric(df: pd.DataFrame, column: str, default: float = 0.0) -> float:
    if df.empty or column not in df.columns:
        return default
    series = pd.to_numeric(df[column], errors="coerce").dropna()
    return float(series.iloc[0]) if not series.empty else default


def _max_numeric(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    series = pd.to_numeric(df[column], errors="coerce").dropna()
    return float(series.max()) if not series.empty else 0.0


def _export(df: pd.DataFrame, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path
