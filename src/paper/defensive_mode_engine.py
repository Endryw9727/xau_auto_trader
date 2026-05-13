"""
Dynamic NORMAL / DEFENSIVE / PAUSE paper-mode simulation.

The engine consumes local paper candidate rows and recalculates a paper equity
path. Mode decisions use only trades closed before the current candidate entry,
so the current trade outcome cannot influence its own mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.paper.paper_degradation import HIGH_MARGIN_STRATEGY_NAME
from src.paper.paper_engine import (
    PaperTradingConfig,
    axi_cost_components_for_lot,
    lot_size_for_equity,
    paper_cost_profile,
)
from src.paper.paper_monitor import DEFAULT_MONITOR_STRATEGY_NAME, PaperReports, max_consecutive_losses, profit_factor, win_rate


MODE_NORMAL = "NORMAL"
MODE_DEFENSIVE = "DEFENSIVE"
MODE_PAUSE = "PAUSE"

VARIANT_MAIN_ALWAYS = "main_always_active"
VARIANT_HIGH_MARGIN_ALWAYS = "high_margin_always_active"
VARIANT_DYNAMIC = "dynamic_normal_defensive_pause"
VARIANT_DYNAMIC_NY18 = "dynamic_plus_no_new_york_18"

DEFAULT_DYNAMIC_DEFENSIVE_SUMMARY_PATH = Path("reports/paper/dynamic_defensive_paper_simulation.csv")
DEFAULT_DYNAMIC_DEFENSIVE_TIMELINE_PATH = Path("reports/paper/dynamic_defensive_mode_timeline.csv")
DEFAULT_DYNAMIC_DEFENSIVE_AUDIT_PATH = Path("reports/paper/dynamic_defensive_trade_audit.csv")

SUMMARY_COLUMNS = [
    "variant_name",
    "total_trades",
    "trades_per_day",
    "profit_factor_net",
    "ending_equity",
    "max_drawdown_pct",
    "max_drawdown_eur",
    "win_rate",
    "expectancy",
    "max_consecutive_losses",
    "profit_factor_last_30",
    "profit_factor_last_50",
    "profit_factor_last_100",
    "months_positive",
    "months_negative",
    "worst_month",
    "worst_week",
    "worst_day",
    "days_in_normal",
    "days_in_defensive",
    "days_in_pause",
    "trades_avoided_by_defensive",
    "trades_avoided_by_pause",
    "trades_avoided_by_research_filter",
    "allow_live",
]
TIMELINE_COLUMNS = [
    "variant_name",
    "decision_time",
    "date",
    "mode",
    "selected_strategy",
    "candidate_main_available",
    "candidate_high_margin_available",
    "decision_trade_count",
    "decision_profit_factor_last_50",
    "decision_current_drawdown_pct",
    "decision_current_loss_streak",
    "decision_weekly_loss_pct",
    "action",
    "skip_reason",
]
AUDIT_COLUMNS = [
    "variant_name",
    "paper_order_id",
    "entry_time",
    "exit_time",
    "mode",
    "selected_strategy",
    "source_strategy",
    "side",
    "session",
    "hour",
    "score",
    "price_points",
    "lot_size",
    "gross_pnl_eur",
    "commission_eur",
    "spread_cost_eur",
    "slippage_cost_eur",
    "total_cost_eur",
    "pnl_eur",
    "equity_before",
    "equity_after",
    "running_equity_high",
    "drawdown_eur",
    "drawdown_percent",
    "decision_trade_count",
    "decision_profit_factor_last_50",
    "decision_current_drawdown_pct",
    "decision_current_loss_streak",
    "decision_weekly_loss_pct",
    "signal_reason",
]


@dataclass(frozen=True)
class ModeState:
    """Entry-known state used to select the paper mode."""

    trade_count: int
    profit_factor_last_50: float
    pf_sample_size: int
    current_drawdown_pct: float
    current_loss_streak: int
    weekly_loss_pct: float
    equity: float
    running_high: float


@dataclass(frozen=True)
class ModeDecision:
    """One mode decision and its reasons."""

    mode: str
    reasons: tuple[str, ...]


def decide_mode_from_state(state: ModeState) -> ModeDecision:
    """Decide NORMAL, DEFENSIVE, or PAUSE from prior closed trades only."""
    pf_gate_active = state.pf_sample_size >= 50
    pause_reasons = []
    if pf_gate_active and state.profit_factor_last_50 < 1.00:
        pause_reasons.append(f"PF50 {state.profit_factor_last_50:.2f} < 1.00")
    if state.current_drawdown_pct > 12.0:
        pause_reasons.append(f"DD corrente {state.current_drawdown_pct:.2f}% > 12%")
    if state.current_loss_streak > 10:
        pause_reasons.append(f"loss streak attuale {state.current_loss_streak} > 10")
    if state.weekly_loss_pct > 8.0:
        pause_reasons.append(f"perdita settimanale {state.weekly_loss_pct:.2f}% > 8%")
    if pause_reasons:
        return ModeDecision(MODE_PAUSE, tuple(pause_reasons))

    defensive_reasons = []
    if pf_gate_active and 1.00 <= state.profit_factor_last_50 < 1.10:
        defensive_reasons.append(f"PF50 {state.profit_factor_last_50:.2f} tra 1.00 e 1.10")
    if 8.0 <= state.current_drawdown_pct <= 12.0:
        defensive_reasons.append(f"DD corrente {state.current_drawdown_pct:.2f}% tra 8% e 12%")
    if 5 <= state.current_loss_streak <= 10:
        defensive_reasons.append(f"loss streak attuale {state.current_loss_streak} tra 5 e 10")
    if defensive_reasons:
        return ModeDecision(MODE_DEFENSIVE, tuple(defensive_reasons))

    return ModeDecision(MODE_NORMAL, ("PF/DD/loss streak inside NORMAL limits",))


def build_mode_state(
    executed_trades: pd.DataFrame,
    current_time: pd.Timestamp,
    initial_equity: float = 1000.0,
) -> ModeState:
    """Build state from trades closed before current_time."""
    closed = _closed_before(executed_trades, current_time)
    if closed.empty:
        return ModeState(
            trade_count=0,
            profit_factor_last_50=float("inf"),
            pf_sample_size=0,
            current_drawdown_pct=0.0,
            current_loss_streak=0,
            weekly_loss_pct=0.0,
            equity=initial_equity,
            running_high=initial_equity,
        )

    pnl = pd.to_numeric(closed["pnl_eur"], errors="coerce").fillna(0.0)
    equity = float(pd.to_numeric(closed["equity_after"], errors="coerce").iloc[-1])
    running_high = float(pd.to_numeric(closed["running_equity_high"], errors="coerce").iloc[-1])
    drawdown_pct = (running_high - equity) / running_high * 100 if running_high > 0 else 0.0
    last_50 = pnl.tail(50)
    return ModeState(
        trade_count=int(len(closed)),
        profit_factor_last_50=profit_factor(last_50),
        pf_sample_size=int(len(last_50)),
        current_drawdown_pct=float(drawdown_pct),
        current_loss_streak=max_trailing_losses_for_closed(closed),
        weekly_loss_pct=weekly_loss_pct(closed, current_time),
        equity=equity,
        running_high=running_high,
    )


def run_dynamic_defensive_paper_simulation(
    reports: PaperReports,
    config: PaperTradingConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run static and dynamic paper-mode variants."""
    candidates = prepare_candidate_trades(reports.trades)
    calendar_days = _calendar_days(reports.daily_summary, DEFAULT_MONITOR_STRATEGY_NAME)
    variants = [
        (VARIANT_MAIN_ALWAYS, MODE_NORMAL, False),
        (VARIANT_HIGH_MARGIN_ALWAYS, MODE_DEFENSIVE, False),
        (VARIANT_DYNAMIC, None, False),
        (VARIANT_DYNAMIC_NY18, None, True),
    ]

    summaries = []
    timelines = []
    audits = []
    for variant_name, forced_mode, filter_new_york_18 in variants:
        summary, timeline, audit = simulate_mode_variant(
            candidates=candidates,
            config=config,
            variant_name=variant_name,
            forced_mode=forced_mode,
            filter_new_york_18=filter_new_york_18,
            calendar_days=calendar_days,
        )
        summaries.append(summary)
        timelines.append(timeline)
        audits.append(audit)
    return (
        pd.DataFrame(summaries, columns=SUMMARY_COLUMNS),
        pd.concat(timelines, ignore_index=True) if timelines else pd.DataFrame(columns=TIMELINE_COLUMNS),
        pd.concat(audits, ignore_index=True) if audits else pd.DataFrame(columns=AUDIT_COLUMNS),
    )


def simulate_mode_variant(
    candidates: pd.DataFrame,
    config: PaperTradingConfig,
    variant_name: str,
    forced_mode: str | None = None,
    filter_new_york_18: bool = False,
    calendar_days: int = 0,
) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Simulate one static or dynamic mode variant."""
    equity = config.initial_equity
    running_high = equity
    open_until = pd.Timestamp.min
    current_day = None
    daily_trade_count = 0
    mode_timeline = []
    audit_rows = []
    profile = paper_cost_profile(config)
    sizing = config.sizing_config

    for entry_time, group in candidates.groupby("entry_time", sort=True):
        entry_time = pd.Timestamp(entry_time)
        if pd.notna(open_until) and entry_time < open_until:
            mode_timeline.append(_timeline_skip_row(variant_name, entry_time, "OPEN_TRADE", group, "open_trade"))
            continue

        trade_day = entry_time.date()
        if current_day != trade_day:
            current_day = trade_day
            daily_trade_count = 0

        executed_df = pd.DataFrame(audit_rows, columns=AUDIT_COLUMNS)
        state = build_mode_state(executed_df, entry_time, initial_equity=config.initial_equity)
        decision = ModeDecision(forced_mode, ("forced mode",)) if forced_mode else decide_mode_from_state(state)
        mode = decision.mode
        main_candidate = _candidate_for(group, DEFAULT_MONITOR_STRATEGY_NAME)
        high_candidate = _candidate_for(group, HIGH_MARGIN_STRATEGY_NAME)
        selected = select_candidate_for_mode(mode, main_candidate, high_candidate)
        skip_reason = ""
        action = "EXECUTE" if selected is not None else "SKIP"

        if daily_trade_count >= config.max_trades_per_day:
            selected = None
            action = "SKIP"
            skip_reason = "daily_trade_limit"
        elif mode == MODE_PAUSE:
            selected = None
            action = "SKIP"
            skip_reason = "pause_mode"
        elif selected is None:
            skip_reason = "no_candidate_for_mode"
        elif filter_new_york_18 and is_new_york_18(selected):
            selected = None
            action = "SKIP"
            skip_reason = "research_filter_new_york_18"

        selected_strategy = str(selected["strategy_name"]) if selected is not None else ""
        mode_timeline.append(
            {
                "variant_name": variant_name,
                "decision_time": entry_time,
                "date": entry_time.date().isoformat(),
                "mode": mode,
                "selected_strategy": selected_strategy,
                "candidate_main_available": main_candidate is not None,
                "candidate_high_margin_available": high_candidate is not None,
                "decision_trade_count": state.trade_count,
                "decision_profit_factor_last_50": state.profit_factor_last_50,
                "decision_current_drawdown_pct": state.current_drawdown_pct,
                "decision_current_loss_streak": state.current_loss_streak,
                "decision_weekly_loss_pct": state.weekly_loss_pct,
                "action": action,
                "skip_reason": skip_reason,
            }
        )

        if selected is None:
            continue

        lot = lot_size_for_equity(equity, sizing)
        price_points = float(pd.to_numeric(selected.get("price_points"), errors="coerce"))
        gross_pnl = price_points * (lot / 0.01) * sizing.eur_per_price_point_per_001_lot
        spread_cost, slippage_cost, commission_cost = axi_cost_components_for_lot(profile, lot)
        total_cost = spread_cost + slippage_cost + commission_cost
        pnl = gross_pnl - total_cost
        equity_before = equity
        equity += pnl
        running_high = max(running_high, equity)
        drawdown_eur = running_high - equity
        drawdown_pct = drawdown_eur / running_high * 100 if running_high > 0 else 0.0
        exit_time = pd.to_datetime(selected.get("exit_time"), errors="coerce")
        if pd.isna(exit_time):
            exit_time = entry_time
        open_until = max(open_until, pd.Timestamp(exit_time))
        daily_trade_count += 1

        audit_rows.append(
            {
                "variant_name": variant_name,
                "paper_order_id": f"{variant_name}-{len(audit_rows) + 1:06d}",
                "entry_time": entry_time,
                "exit_time": exit_time,
                "mode": mode,
                "selected_strategy": selected_strategy,
                "source_strategy": selected_strategy,
                "side": str(selected.get("side", "")),
                "session": str(selected.get("session", "")),
                "hour": int(entry_time.hour),
                "score": float(pd.to_numeric(selected.get("score"), errors="coerce")) if pd.notna(selected.get("score")) else 0.0,
                "price_points": price_points,
                "lot_size": lot,
                "gross_pnl_eur": gross_pnl,
                "commission_eur": commission_cost,
                "spread_cost_eur": spread_cost,
                "slippage_cost_eur": slippage_cost,
                "total_cost_eur": total_cost,
                "pnl_eur": pnl,
                "equity_before": equity_before,
                "equity_after": equity,
                "running_equity_high": running_high,
                "drawdown_eur": drawdown_eur,
                "drawdown_percent": drawdown_pct,
                "decision_trade_count": state.trade_count,
                "decision_profit_factor_last_50": state.profit_factor_last_50,
                "decision_current_drawdown_pct": state.current_drawdown_pct,
                "decision_current_loss_streak": state.current_loss_streak,
                "decision_weekly_loss_pct": state.weekly_loss_pct,
                "signal_reason": str(selected.get("signal_reason", "")),
            }
        )

    timeline = pd.DataFrame(mode_timeline, columns=TIMELINE_COLUMNS)
    audit = pd.DataFrame(audit_rows, columns=AUDIT_COLUMNS)
    summary = summary_for_variant(variant_name, audit, timeline, config.initial_equity, calendar_days)
    return summary, timeline, audit


def prepare_candidate_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Return candidate rows for main and high-margin paper strategies."""
    if trades.empty:
        return pd.DataFrame()
    result = trades[
        trades["strategy_name"].isin([DEFAULT_MONITOR_STRATEGY_NAME, HIGH_MARGIN_STRATEGY_NAME])
    ].copy()
    result["entry_time"] = pd.to_datetime(result["entry_time"], errors="coerce")
    result["exit_time"] = pd.to_datetime(result["exit_time"], errors="coerce")
    result = result.dropna(subset=["entry_time"]).sort_values(["entry_time", "strategy_name"]).reset_index(drop=True)
    result["session"] = result.get("session", "").fillna("").astype(str).str.upper()
    return result


def select_candidate_for_mode(
    mode: str,
    main_candidate: pd.Series | None,
    high_candidate: pd.Series | None,
) -> pd.Series | None:
    """Select the candidate corresponding to the current mode."""
    if mode == MODE_NORMAL:
        return main_candidate
    if mode == MODE_DEFENSIVE:
        return high_candidate
    return None


def summary_for_variant(
    variant_name: str,
    audit: pd.DataFrame,
    timeline: pd.DataFrame,
    initial_equity: float,
    calendar_days: int,
) -> dict:
    """Calculate requested summary metrics for one variant."""
    pnl = pd.to_numeric(audit.get("pnl_eur", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    if audit.empty:
        ending_equity = initial_equity
        max_dd_pct = max_dd_eur = 0.0
    else:
        ending_equity = float(pd.to_numeric(audit["equity_after"], errors="coerce").iloc[-1])
        max_dd_pct = float(pd.to_numeric(audit["drawdown_percent"], errors="coerce").max())
        max_dd_eur = float(pd.to_numeric(audit["drawdown_eur"], errors="coerce").max())
    period = _period_pnl(audit)
    return {
        "variant_name": variant_name,
        "total_trades": int(len(audit)),
        "trades_per_day": len(audit) / calendar_days if calendar_days else 0.0,
        "profit_factor_net": profit_factor(pnl),
        "ending_equity": ending_equity,
        "max_drawdown_pct": max_dd_pct,
        "max_drawdown_eur": max_dd_eur,
        "win_rate": win_rate(pnl),
        "expectancy": float(pnl.mean()) if len(pnl) else 0.0,
        "max_consecutive_losses": max_consecutive_losses(pnl),
        "profit_factor_last_30": profit_factor(pnl.tail(30)),
        "profit_factor_last_50": profit_factor(pnl.tail(50)),
        "profit_factor_last_100": profit_factor(pnl.tail(100)),
        "months_positive": int((period["M"] > 0).sum()) if not period["M"].empty else 0,
        "months_negative": int((period["M"] < 0).sum()) if not period["M"].empty else 0,
        "worst_month": float(period["M"].min()) if not period["M"].empty else 0.0,
        "worst_week": float(period["W"].min()) if not period["W"].empty else 0.0,
        "worst_day": float(period["D"].min()) if not period["D"].empty else 0.0,
        "days_in_normal": _days_in_mode(timeline, MODE_NORMAL),
        "days_in_defensive": _days_in_mode(timeline, MODE_DEFENSIVE),
        "days_in_pause": _days_in_mode(timeline, MODE_PAUSE),
        "trades_avoided_by_defensive": _avoided_by_defensive(timeline),
        "trades_avoided_by_pause": _avoided_by_pause(timeline),
        "trades_avoided_by_research_filter": int((timeline.get("skip_reason", pd.Series(dtype=str)) == "research_filter_new_york_18").sum()),
        "allow_live": False,
    }


def export_dynamic_defensive_reports(
    summary: pd.DataFrame,
    timeline: pd.DataFrame,
    audit: pd.DataFrame,
    summary_path: str | Path = DEFAULT_DYNAMIC_DEFENSIVE_SUMMARY_PATH,
    timeline_path: str | Path = DEFAULT_DYNAMIC_DEFENSIVE_TIMELINE_PATH,
    audit_path: str | Path = DEFAULT_DYNAMIC_DEFENSIVE_AUDIT_PATH,
) -> tuple[Path, Path, Path]:
    """Export dynamic defensive reports."""
    return (_export(summary, summary_path), _export(timeline, timeline_path), _export(audit, audit_path))


def _closed_before(executed_trades: pd.DataFrame, current_time: pd.Timestamp) -> pd.DataFrame:
    if executed_trades.empty:
        return executed_trades.copy()
    result = executed_trades.copy()
    result["exit_time"] = pd.to_datetime(result["exit_time"], errors="coerce").fillna(pd.to_datetime(result["entry_time"], errors="coerce"))
    return result[result["exit_time"] <= current_time].copy()


def max_trailing_losses_for_closed(closed: pd.DataFrame) -> int:
    """Return trailing losing streak among closed trades."""
    if closed.empty:
        return 0
    pnl = list(pd.to_numeric(closed["pnl_eur"], errors="coerce").fillna(0.0))
    streak = 0
    for value in reversed(pnl):
        if value < 0:
            streak += 1
        else:
            break
    return int(streak)


def weekly_loss_pct(closed: pd.DataFrame, current_time: pd.Timestamp) -> float:
    """Return current-week loss percentage from closed trades only."""
    if closed.empty:
        return 0.0
    result = closed.copy()
    result["exit_time"] = pd.to_datetime(result["exit_time"], errors="coerce")
    week = current_time.to_period("W")
    group = result[result["exit_time"].dt.to_period("W") == week]
    if group.empty:
        return 0.0
    pnl = pd.to_numeric(group["pnl_eur"], errors="coerce").fillna(0.0)
    net = float(pnl.sum())
    if net >= 0:
        return 0.0
    start_equity = float(pd.to_numeric(group["equity_before"], errors="coerce").iloc[0])
    return abs(net) / start_equity * 100 if start_equity > 0 else 0.0


def is_new_york_18(row: pd.Series) -> bool:
    """Return True for the research-only NEW YORK hour-18 filter."""
    entry_time = pd.to_datetime(row.get("entry_time"), errors="coerce")
    session = str(row.get("session", "")).upper()
    return bool(pd.notna(entry_time) and session == "NEW YORK" and int(entry_time.hour) == 18)


def _candidate_for(group: pd.DataFrame, strategy_name: str) -> pd.Series | None:
    match = group[group["strategy_name"] == strategy_name]
    if match.empty:
        return None
    return match.iloc[0]


def _timeline_skip_row(variant_name: str, entry_time: pd.Timestamp, mode: str, group: pd.DataFrame, reason: str) -> dict:
    return {
        "variant_name": variant_name,
        "decision_time": entry_time,
        "date": entry_time.date().isoformat(),
        "mode": mode,
        "selected_strategy": "",
        "candidate_main_available": bool((group["strategy_name"] == DEFAULT_MONITOR_STRATEGY_NAME).any()),
        "candidate_high_margin_available": bool((group["strategy_name"] == HIGH_MARGIN_STRATEGY_NAME).any()),
        "decision_trade_count": 0,
        "decision_profit_factor_last_50": 0.0,
        "decision_current_drawdown_pct": 0.0,
        "decision_current_loss_streak": 0,
        "decision_weekly_loss_pct": 0.0,
        "action": "SKIP",
        "skip_reason": reason,
    }


def _calendar_days(daily_summary: pd.DataFrame, strategy_name: str) -> int:
    if daily_summary.empty:
        return 0
    daily = daily_summary.copy()
    if "strategy_name" in daily.columns:
        daily = daily[daily["strategy_name"] == strategy_name]
    return int(pd.to_datetime(daily["date"], errors="coerce").dropna().dt.normalize().nunique())


def _period_pnl(audit: pd.DataFrame) -> dict[str, pd.Series]:
    if audit.empty:
        empty = pd.Series(dtype=float)
        return {"D": empty, "W": empty, "M": empty}
    result = audit.copy()
    result["entry_time"] = pd.to_datetime(result["entry_time"], errors="coerce")
    result = result.dropna(subset=["entry_time"])
    return {
        "D": result.groupby(result["entry_time"].dt.to_period("D"))["pnl_eur"].sum(),
        "W": result.groupby(result["entry_time"].dt.to_period("W"))["pnl_eur"].sum(),
        "M": result.groupby(result["entry_time"].dt.to_period("M"))["pnl_eur"].sum(),
    }


def _days_in_mode(timeline: pd.DataFrame, mode: str) -> int:
    if timeline.empty:
        return 0
    return int(timeline[timeline["mode"] == mode]["date"].nunique())


def _avoided_by_defensive(timeline: pd.DataFrame) -> int:
    if timeline.empty:
        return 0
    defensive = timeline[timeline["mode"] == MODE_DEFENSIVE]
    return int((defensive["candidate_main_available"] & (defensive["selected_strategy"] != DEFAULT_MONITOR_STRATEGY_NAME)).sum())


def _avoided_by_pause(timeline: pd.DataFrame) -> int:
    if timeline.empty:
        return 0
    paused = timeline[timeline["mode"] == MODE_PAUSE]
    return int((paused["candidate_main_available"] | paused["candidate_high_margin_available"]).sum())


def _export(df: pd.DataFrame, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path
