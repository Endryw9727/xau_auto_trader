"""Run a live-safe V51 demo cycle with data refresh and freshness gates."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Callable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_reasoning.v51_reasoning_engine import (
    CandidateContext,
    MacroContext,
    NewsRiskContext,
    ReasoningDecision,
    ReasoningInput,
    evaluate_v51_reasoning,
    timeframe_contexts_from_records,
)
from src.execution.v51_demo_executor import DEFAULT_V51_DEMO_OUTPUT_DIR, run_v51_demo_execution_once
from src.market_data.data_freshness import DEFAULT_XAUUSD_CSV_PATH, analyze_data_freshness, format_freshness_detail
from src.market_data.mt5_csv_bridge import import_mt5_csv_bridge
from src.market_data.mt5_readonly_data_updater import update_market_data_from_mt5_readonly
from src.strategy_lab.strategy_v51_demo_intraday import DEFAULT_V51_CONFIG_PATH, load_v51_config
from scripts.run_v51_mtf_context_report import run_v51_mtf_context_report
from scripts.update_mt5_timeframes import run_mt5_timeframe_update


DEFAULT_V51_LIVE_SAFE_CYCLE_LOG_PATH = DEFAULT_V51_DEMO_OUTPUT_DIR / "v51_live_safe_cycle.log"
DEFAULT_V51_DECISION_AUDIT_CSV_PATH = DEFAULT_V51_DEMO_OUTPUT_DIR / "v51_decision_audit.csv"
DEFAULT_V51_DECISION_AUDIT_LATEST_PATH = DEFAULT_V51_DEMO_OUTPUT_DIR / "v51_decision_audit_latest.txt"

V51_DECISION_AUDIT_COLUMNS = [
    "timestamp",
    "mode",
    "symbol",
    "now_utc",
    "now_local",
    "mt5_timestamp_timezone",
    "latest_closed_candle_time",
    "latest_closed_candle_time_raw",
    "latest_closed_candle_time_utc",
    "latest_closed_candle_age_minutes",
    "current_bid",
    "current_ask",
    "spread_points",
    "mtf_context_status",
    "mtf_final_bias",
    "mtf_filter_enabled",
    "mtf_filter_passed",
    "mtf_filter_reason",
    "ai_reasoning_enabled",
    "ai_reasoning_report_only",
    "ai_final_bias",
    "ai_confidence_score",
    "ai_trade_quality_score",
    "ai_allow_trade",
    "ai_veto_reasons",
    "ai_positive_factors",
    "ai_negative_factors",
    "ai_explanation",
    "v51_called",
    "v51_status",
    "v51_accepted",
    "signal_id",
    "side",
    "selected_candidate_time",
    "selected_candidate_time_raw",
    "selected_candidate_time_utc",
    "candidate_age_minutes",
    "candidate_time_basis",
    "time_alignment_status",
    "expected_entry_price",
    "slippage_points",
    "max_slippage_points",
    "score",
    "risk_reward",
    "final_reason",
    "dry_run",
]


@dataclass(frozen=True)
class V51LiveSafeCycleResult:
    """Outcome of one V51 live-safe data refresh and demo execution cycle."""

    status: str
    reason: str
    data_update_statuses: tuple[str, ...]
    csv_import_statuses: tuple[str, ...]
    timeframe_update_status: str
    mtf_context_status: str
    mtf_final_bias: str | None
    freshness_status: str
    v51_called: bool
    v51_status: str | None = None
    v51_accepted: bool | None = None


def run_v51_live_safe_cycle(
    *,
    config_path: str | Path = DEFAULT_V51_CONFIG_PATH,
    output_dir: str | Path = DEFAULT_V51_DEMO_OUTPUT_DIR,
    data_path: str | Path = DEFAULT_XAUUSD_CSV_PATH,
    log_path: str | Path = DEFAULT_V51_LIVE_SAFE_CYCLE_LOG_PATH,
    execute_demo: bool = False,
    now: pd.Timestamp | None = None,
    update_data_fn: Callable[..., list[Any]] = update_market_data_from_mt5_readonly,
    import_bridge_fn: Callable[..., list[Any]] = import_mt5_csv_bridge,
    update_timeframes_fn: Callable[..., Any] = run_mt5_timeframe_update,
    mtf_context_fn: Callable[..., Any] = run_v51_mtf_context_report,
    freshness_fn: Callable[..., Any] = analyze_data_freshness,
    execution_fn: Callable[..., Any] = run_v51_demo_execution_once,
) -> V51LiveSafeCycleResult:
    """Refresh read-only data, block stale data, then optionally run V51 demo execution."""
    log_path = Path(log_path)
    lines = [_header("V51 LIVE SAFE CYCLE START")]

    try:
        config = load_v51_config(config_path)
    except Exception as exc:
        result = V51LiveSafeCycleResult(
            status="SAFETY_ERROR",
            reason=str(exc),
            data_update_statuses=(),
            csv_import_statuses=(),
            timeframe_update_status="NOT_RUN",
            mtf_context_status="NOT_RUN",
            mtf_final_bias=None,
            freshness_status="NOT_CHECKED",
            v51_called=False,
        )
        lines.append(f"SAFETY_ERROR {result.reason}")
        lines.append("No real live execution is enabled.")
        write_decision_audit(
            output_dir,
            mode=_cycle_mode(execute_demo),
            config=None,
            freshness=None,
            mtf_context=None,
            cycle_result=result,
            execution=None,
            ai_decision=None,
            dry_run=not execute_demo,
        )
        append_cycle_log(log_path, lines)
        return result

    if config.allow_real_live:
        result = V51LiveSafeCycleResult(
            status="SAFETY_ERROR",
            reason="allow_real_live=true blocks V51 live-safe cycle",
            data_update_statuses=(),
            csv_import_statuses=(),
            timeframe_update_status="NOT_RUN",
            mtf_context_status="NOT_RUN",
            mtf_final_bias=None,
            freshness_status="NOT_CHECKED",
            v51_called=False,
        )
        lines.append(result.reason)
        lines.append("No real live execution is enabled.")
        write_decision_audit(
            output_dir,
            mode=_cycle_mode(execute_demo),
            config=config,
            freshness=None,
            mtf_context=None,
            cycle_result=result,
            execution=None,
            ai_decision=None,
            dry_run=not execute_demo,
        )
        append_cycle_log(log_path, lines)
        return result

    update_results = _safe_call_results("MT5_READONLY_UPDATE", update_data_fn, lines)
    import_results = _safe_call_results("MT5_CSV_BRIDGE_IMPORT", import_bridge_fn, lines)
    data_update_statuses = _result_statuses(update_results)
    csv_import_statuses = _result_statuses(import_results)
    timeframe_update = _safe_call_single("MT5_TIMEFRAME_UPDATE", update_timeframes_fn, lines)
    timeframe_update_status = str(getattr(timeframe_update, "status", "ERROR"))
    mtf_context = _safe_call_single("V51_MTF_CONTEXT", mtf_context_fn, lines, config_path=config_path)
    mtf_context_status = str(getattr(mtf_context, "status", "ERROR"))
    mtf_final_bias = getattr(mtf_context, "final_bias", None)

    freshness = _call_freshness(freshness_fn, data_path, now, config=config)
    freshness_status = str(getattr(freshness, "status", "ERROR"))
    freshness_detail = format_freshness_detail(freshness)
    lines.append(f"DATA_FRESHNESS {freshness_detail}")

    if not bool(getattr(freshness, "is_fresh", False)):
        result = V51LiveSafeCycleResult(
            status="DATA_STALE",
            reason=freshness_detail,
            data_update_statuses=data_update_statuses,
            csv_import_statuses=csv_import_statuses,
            timeframe_update_status=timeframe_update_status,
            mtf_context_status=mtf_context_status,
            mtf_final_bias=None if mtf_final_bias is None else str(mtf_final_bias),
            freshness_status=freshness_status,
            v51_called=False,
        )
        lines.append(f"DATA_STALE {freshness_detail}")
        lines.append("V51 demo execution skipped because local data is not fresh.")
        lines.append("No real live execution is enabled.")
        ai_decision = build_ai_reasoning_decision(config, mtf_context, freshness, execution=None)
        write_decision_audit(
            output_dir,
            mode=_cycle_mode(execute_demo),
            config=config,
            freshness=freshness,
            mtf_context=mtf_context,
            cycle_result=result,
            execution=None,
            ai_decision=ai_decision,
            dry_run=not execute_demo,
        )
        append_cycle_log(log_path, lines)
        return result

    execution, ai_decision = run_execution_with_ai_reasoning(
        execution_fn,
        config=config,
        config_path=config_path,
        output_dir=output_dir,
        mtf_context_summary_path=getattr(mtf_context, "summary_path", None),
        mtf_context=mtf_context,
        freshness=freshness,
        execute_demo=execute_demo,
        now=now,
    )
    result = V51LiveSafeCycleResult(
        status="V51_EXECUTED",
        reason=str(getattr(execution, "reason", "")),
        data_update_statuses=data_update_statuses,
        csv_import_statuses=csv_import_statuses,
        timeframe_update_status=timeframe_update_status,
        mtf_context_status=mtf_context_status,
        mtf_final_bias=None if mtf_final_bias is None else str(mtf_final_bias),
        freshness_status=freshness_status,
        v51_called=True,
        v51_status=str(getattr(execution, "status", "")),
        v51_accepted=bool(getattr(execution, "accepted", False)),
    )
    lines.append(
        "V51_DEMO_EXECUTION "
        f"status={result.v51_status} accepted={result.v51_accepted} reason={result.reason}"
    )
    lines.append("No real live execution is enabled.")
    write_decision_audit(
        output_dir,
        mode=_cycle_mode(execute_demo),
        config=config,
        freshness=freshness,
        mtf_context=mtf_context,
        cycle_result=result,
        execution=execution,
        ai_decision=ai_decision,
        dry_run=bool(getattr(execution, "dry_run", not execute_demo)),
    )
    append_cycle_log(log_path, lines)
    return result


def write_decision_audit(
    output_dir: str | Path,
    *,
    mode: str,
    config: Any | None,
    freshness: Any | None,
    mtf_context: Any | None,
    cycle_result: V51LiveSafeCycleResult,
    execution: Any | None,
    ai_decision: ReasoningDecision | None,
    dry_run: bool,
) -> tuple[Path, Path]:
    """Append one cycle audit row and refresh the human-readable latest file."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    csv_path = output_path / DEFAULT_V51_DECISION_AUDIT_CSV_PATH.name
    latest_path = output_path / DEFAULT_V51_DECISION_AUDIT_LATEST_PATH.name
    row = build_decision_audit_row(
        mode=mode,
        config=config,
        freshness=freshness,
        mtf_context=mtf_context,
        cycle_result=cycle_result,
        execution=execution,
        ai_decision=ai_decision,
        dry_run=dry_run,
    )
    _append_csv(csv_path, row, V51_DECISION_AUDIT_COLUMNS)
    latest_path.write_text(
        build_decision_audit_latest_text(
            row,
            freshness=freshness,
            mtf_context=mtf_context,
            cycle_result=cycle_result,
            execution=execution,
            ai_decision=ai_decision,
        ),
        encoding="utf-8",
    )
    return csv_path, latest_path


def build_decision_audit_row(
    *,
    mode: str,
    config: Any | None,
    freshness: Any | None,
    mtf_context: Any | None,
    cycle_result: V51LiveSafeCycleResult,
    execution: Any | None,
    ai_decision: ReasoningDecision | None,
    dry_run: bool,
) -> dict[str, Any]:
    """Build one flat V51 cycle audit row from existing read-only telemetry."""
    latest_closed = _first_present(
        getattr(execution, "latest_closed_candle_time", None),
        getattr(freshness, "latest_timestamp", None),
    )
    latest_closed_raw = _first_present(
        getattr(execution, "latest_closed_candle_time_raw", None),
        _timestamp_text(getattr(freshness, "latest_timestamp", None)),
    )
    latest_closed_utc = _first_present(
        getattr(execution, "latest_closed_candle_time_utc", None),
        latest_closed,
    )
    selected_candidate_utc = _first_present(
        getattr(execution, "selected_candidate_time_utc", None),
        getattr(execution, "selected_candidate_time", None),
    )
    mt5_timezone = _first_present(
        getattr(execution, "mt5_timestamp_timezone", None),
        getattr(config, "mt5_timestamp_timezone", None),
        "Europe/Rome",
    )
    mtf_filter_enabled = _first_present(
        getattr(execution, "mtf_filter_enabled", None),
        getattr(config, "use_mtf_context_filter", None),
    )
    mtf_filter_passed = getattr(execution, "mtf_filter_passed", None)
    mtf_filter_reason = _first_present(
        getattr(execution, "mtf_filter_reason", None),
        "v51_not_called" if not cycle_result.v51_called else None,
    )
    mtf_final_bias = _first_present(
        getattr(execution, "mtf_final_bias", None),
        getattr(mtf_context, "final_bias", None),
        cycle_result.mtf_final_bias,
    )
    return {
        "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
        "mode": mode,
        "symbol": getattr(config, "symbol", None),
        "now_utc": _utc_timestamp_text(
            _first_present(getattr(execution, "now_utc", None), getattr(freshness, "checked_at", None)),
            str(mt5_timezone),
        ),
        "now_local": _first_present(
            getattr(execution, "now_local", None),
            _local_timestamp_text(getattr(freshness, "checked_at", None), str(mt5_timezone)),
        ),
        "mt5_timestamp_timezone": mt5_timezone,
        "latest_closed_candle_time": _timestamp_text(latest_closed),
        "latest_closed_candle_time_raw": latest_closed_raw,
        "latest_closed_candle_time_utc": _utc_timestamp_text(latest_closed_utc, str(mt5_timezone)),
        "latest_closed_candle_age_minutes": _float_or_none(getattr(freshness, "age_minutes", None)),
        "current_bid": _float_or_none(getattr(execution, "current_bid", None)),
        "current_ask": _float_or_none(getattr(execution, "current_ask", None)),
        "spread_points": _float_or_none(getattr(execution, "spread_points", None)),
        "mtf_context_status": cycle_result.mtf_context_status,
        "mtf_final_bias": None if mtf_final_bias is None else str(mtf_final_bias),
        "mtf_filter_enabled": mtf_filter_enabled,
        "mtf_filter_passed": mtf_filter_passed,
        "mtf_filter_reason": mtf_filter_reason,
        "ai_reasoning_enabled": getattr(config, "use_ai_reasoning_filter", None),
        "ai_reasoning_report_only": getattr(config, "ai_reasoning_report_only", None),
        "ai_final_bias": getattr(ai_decision, "final_bias", None),
        "ai_confidence_score": _float_or_none(getattr(ai_decision, "confidence_score", None)),
        "ai_trade_quality_score": _float_or_none(getattr(ai_decision, "trade_quality_score", None)),
        "ai_allow_trade": getattr(ai_decision, "allow_trade", None),
        "ai_veto_reasons": _join_reasoning_list(getattr(ai_decision, "veto_reasons", None)),
        "ai_positive_factors": _join_reasoning_list(getattr(ai_decision, "positive_factors", None)),
        "ai_negative_factors": _join_reasoning_list(getattr(ai_decision, "negative_factors", None)),
        "ai_explanation": getattr(ai_decision, "explanation", None),
        "v51_called": cycle_result.v51_called,
        "v51_status": cycle_result.v51_status,
        "v51_accepted": cycle_result.v51_accepted,
        "signal_id": getattr(execution, "signal_id", None),
        "side": getattr(execution, "side", None),
        "selected_candidate_time": _timestamp_text(getattr(execution, "selected_candidate_time", None)),
        "selected_candidate_time_raw": getattr(execution, "selected_candidate_time_raw", None),
        "selected_candidate_time_utc": _utc_timestamp_text(selected_candidate_utc, str(mt5_timezone)),
        "candidate_age_minutes": _float_or_none(getattr(execution, "candidate_age_minutes", None)),
        "candidate_time_basis": getattr(execution, "candidate_time_basis", None),
        "time_alignment_status": getattr(execution, "time_alignment_status", None),
        "expected_entry_price": _float_or_none(getattr(execution, "expected_entry_price", None)),
        "slippage_points": _float_or_none(getattr(execution, "slippage_points", None)),
        "max_slippage_points": _first_present(
            _float_or_none(getattr(execution, "max_slippage_points", None)),
            _float_or_none(getattr(config, "max_slippage_points", None)),
        ),
        "score": _float_or_none(getattr(execution, "score", None)),
        "risk_reward": _float_or_none(getattr(execution, "risk_reward", None)),
        "final_reason": cycle_result.reason,
        "dry_run": dry_run,
    }


def build_decision_audit_latest_text(
    row: dict[str, Any],
    *,
    freshness: Any | None,
    mtf_context: Any | None,
    cycle_result: V51LiveSafeCycleResult,
    execution: Any | None,
    ai_decision: ReasoningDecision | None,
) -> str:
    """Build a concise latest-cycle audit summary for operators."""
    lines = [
        "V51 Decision Audit",
        f"Generated at: {row['timestamp']}",
        "",
        "Market data freshness",
        f"- status: {cycle_result.freshness_status}",
        f"- latest_closed_candle_time: {row['latest_closed_candle_time'] or 'n/a'}",
        f"- latest_closed_candle_age_minutes: {_display(row['latest_closed_candle_age_minutes'])}",
        f"- detail: {format_freshness_detail(freshness) if freshness is not None else cycle_result.reason}",
        "",
        "Time alignment",
        f"- now_utc: {row['now_utc'] or 'n/a'}",
        f"- now_local: {row['now_local'] or 'n/a'}",
        f"- mt5_timestamp_timezone: {row['mt5_timestamp_timezone'] or 'n/a'}",
        f"- latest_closed_candle_time_raw: {row['latest_closed_candle_time_raw'] or 'n/a'}",
        f"- latest_closed_candle_time_utc: {row['latest_closed_candle_time_utc'] or 'n/a'}",
        f"- selected_candidate_time_raw: {row['selected_candidate_time_raw'] or 'n/a'}",
        f"- selected_candidate_time_utc: {row['selected_candidate_time_utc'] or 'n/a'}",
        f"- candidate_time_basis: {row['candidate_time_basis'] or 'n/a'}",
        f"- time_alignment_status: {row['time_alignment_status'] or 'n/a'}",
        "",
        "MTF context",
        f"- status: {cycle_result.mtf_context_status}",
        f"- final_bias: {row['mtf_final_bias'] or 'n/a'}",
    ]
    timeframe_lines = _mtf_timeframe_summary_lines(mtf_context)
    if timeframe_lines:
        lines.append("- timeframe bias:")
        lines.extend(f"  - {line}" for line in timeframe_lines)
    else:
        lines.append("- timeframe bias: unavailable")
    lines.extend(
        [
            "",
            "AI reasoning",
            f"- enabled: {_display(row['ai_reasoning_enabled'])}",
            f"- report_only: {_display(row['ai_reasoning_report_only'])}",
            f"- final_bias: {row['ai_final_bias'] or 'n/a'}",
            f"- confidence_score: {_display(row['ai_confidence_score'])}",
            f"- trade_quality_score: {_display(row['ai_trade_quality_score'])}",
            f"- allow_trade: {_display(row['ai_allow_trade'])}",
            f"- veto_reasons: {row['ai_veto_reasons'] or 'n/a'}",
            f"- positive_factors: {row['ai_positive_factors'] or 'n/a'}",
            f"- negative_factors: {row['ai_negative_factors'] or 'n/a'}",
            f"- explanation: {row['ai_explanation'] or 'n/a'}",
            "",
            "Candidate status",
            f"- v51_called: {row['v51_called']}",
            f"- v51_status: {row['v51_status'] or 'n/a'}",
            f"- v51_accepted: {_display(row['v51_accepted'])}",
            f"- signal_id: {row['signal_id'] or 'n/a'}",
            f"- side: {row['side'] or 'n/a'}",
            f"- selected_candidate_time: {row['selected_candidate_time'] or 'n/a'}",
            f"- candidate_age_minutes: {_display(row['candidate_age_minutes'])}",
            f"- score: {_display(row['score'])}",
            f"- risk_reward: {_display(row['risk_reward'])}",
            "",
            "Final decision",
            f"- mode: {row['mode']}",
            f"- mtf_filter_enabled: {_display(row['mtf_filter_enabled'])}",
            f"- mtf_filter_passed: {_display(row['mtf_filter_passed'])}",
            f"- mtf_filter_reason: {row['mtf_filter_reason'] or 'n/a'}",
            f"- current_bid: {_display(row['current_bid'])}",
            f"- current_ask: {_display(row['current_ask'])}",
            f"- spread_points: {_display(row['spread_points'])}",
            f"- slippage_points: {_display(row['slippage_points'])}",
            f"- max_slippage_points: {_display(row['max_slippage_points'])}",
            f"- exact_rejection_reason: {cycle_result.reason}",
        ]
    )
    if execution is not None and getattr(execution, "reason", None):
        lines.append(f"- executor_reason: {getattr(execution, 'reason')}")
    if ai_decision is not None and ai_decision.veto_reasons:
        lines.append(f"- ai_veto_reasons: {', '.join(ai_decision.veto_reasons)}")
    return "\n".join(lines) + "\n"


def run_execution_with_ai_reasoning(
    execution_fn: Callable[..., Any],
    *,
    config: Any,
    config_path: str | Path,
    output_dir: str | Path,
    mtf_context_summary_path: str | Path | None,
    mtf_context: Any | None,
    freshness: Any | None,
    execute_demo: bool,
    now: pd.Timestamp | None,
) -> tuple[Any, ReasoningDecision | None]:
    """Run V51 execution and optionally enforce the AI reasoning veto before demo submit."""
    base_kwargs = {
        "config_path": config_path,
        "output_dir": output_dir,
        "mtf_context_summary_path": mtf_context_summary_path,
    }
    if now is not None:
        base_kwargs["now"] = now

    if not _ai_reasoning_enforcement_enabled(config):
        execution = execution_fn(dry_run=not execute_demo, **base_kwargs)
        ai_decision = build_ai_reasoning_decision(config, mtf_context, freshness, execution=execution)
        return execution, ai_decision

    preview = execution_fn(dry_run=True, **base_kwargs)
    ai_decision = build_ai_reasoning_decision(config, mtf_context, freshness, execution=preview)
    if _ai_reasoning_blocks_execution(config, ai_decision, preview):
        return _ai_blocked_execution(preview, ai_decision), ai_decision
    if execute_demo and bool(getattr(preview, "accepted", False)):
        execution = execution_fn(dry_run=False, **base_kwargs)
        return execution, ai_decision
    return preview, ai_decision


def build_ai_reasoning_decision(
    config: Any | None,
    mtf_context: Any | None,
    freshness: Any | None,
    *,
    execution: Any | None,
) -> ReasoningDecision | None:
    """Evaluate deterministic V51 AI reasoning from existing telemetry."""
    if config is None:
        return None
    reasoning_input = ReasoningInput(
        timeframes=_load_ai_timeframe_contexts(mtf_context),
        candidate=_candidate_context_from_execution(config, execution),
        macro=MacroContext(
            session=getattr(execution, "session", None),
            market_open=bool(getattr(freshness, "market_open", True)),
        ),
        news_risk=NewsRiskContext(),
        mtf_final_bias=_first_present(getattr(execution, "mtf_final_bias", None), getattr(mtf_context, "final_bias", None)),
        mtf_context_status=getattr(mtf_context, "status", None),
        min_confidence_to_trade=float(getattr(config, "min_ai_confidence_to_trade", 70)),
        min_trade_quality_score=float(getattr(config, "min_trade_quality_score", 70)),
    )
    return evaluate_v51_reasoning(reasoning_input)


def _ai_reasoning_enforcement_enabled(config: Any) -> bool:
    return bool(getattr(config, "use_ai_reasoning_filter", False)) and not bool(
        getattr(config, "ai_reasoning_report_only", True)
    )


def _ai_reasoning_blocks_execution(config: Any, decision: ReasoningDecision | None, execution: Any) -> bool:
    if not _ai_reasoning_enforcement_enabled(config):
        return False
    if decision is None:
        return False
    return bool(getattr(execution, "accepted", False)) and not decision.allow_trade


def _ai_blocked_execution(execution: Any, decision: ReasoningDecision | None) -> Any:
    values = dict(getattr(execution, "__dict__", {}))
    if not values:
        values = {
            "signal_id": getattr(execution, "signal_id", None),
            "side": getattr(execution, "side", None),
            "dry_run": True,
        }
    veto = ", ".join(decision.veto_reasons) if decision is not None else "ai_reasoning_veto"
    values.update(
        {
            "accepted": False,
            "status": "NO_TRADE",
            "reason": f"ai_reasoning_filter_blocked: {veto}",
            "dry_run": True,
        }
    )
    return SimpleNamespace(**values)


def _candidate_context_from_execution(config: Any, execution: Any | None) -> CandidateContext | None:
    if execution is None or not getattr(execution, "side", None):
        return None
    return CandidateContext(
        side=str(getattr(execution, "side")),
        score=_float_or_none(getattr(execution, "score", None)),
        score_gap=_float_or_none(getattr(execution, "score_gap", None)),
        risk_reward=_float_or_none(getattr(execution, "risk_reward", None)),
        session=getattr(execution, "session", None),
        spread_points=_float_or_none(getattr(execution, "spread_points", None)),
        max_spread_points=_float_or_none(getattr(config, "max_spread_points", None)),
        slippage_points=_first_present(
            _float_or_none(getattr(execution, "slippage_points", None)),
            _float_or_none(getattr(execution, "adverse_slippage_points", None)),
        ),
        max_slippage_points=_first_present(
            _float_or_none(getattr(execution, "max_slippage_points", None)),
            _float_or_none(getattr(config, "max_slippage_points", None)),
        ),
        expected_entry_price=_float_or_none(getattr(execution, "expected_entry_price", None)),
    )


def _load_ai_timeframe_contexts(mtf_context: Any | None) -> tuple[Any, ...]:
    summary_path = getattr(mtf_context, "summary_path", None)
    if summary_path is None:
        return ()
    path = Path(summary_path)
    if not path.exists():
        return ()
    try:
        summary = pd.read_csv(path)
    except Exception:
        return ()
    if summary.empty:
        return ()
    return timeframe_contexts_from_records(summary.to_dict("records"))


def append_cycle_log(path: str | Path, lines: list[str]) -> Path:
    """Append cycle lines to the V51 demo execution log."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as file:
        for line in lines:
            file.write(line.rstrip() + "\n")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Run V51 in dry-run mode after data freshness passes.")
    mode.add_argument("--execute-demo", action="store_true", help="Run V51 demo execution after data freshness passes.")
    parser.add_argument("--config", type=Path, default=DEFAULT_V51_CONFIG_PATH, help="V51 strategy config path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_V51_DEMO_OUTPUT_DIR, help="V51 demo output directory.")
    parser.add_argument("--data-path", type=Path, default=DEFAULT_XAUUSD_CSV_PATH, help="Local M15 CSV checked for freshness.")
    parser.add_argument("--log-path", type=Path, default=DEFAULT_V51_LIVE_SAFE_CYCLE_LOG_PATH, help="Cycle log path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    execute_demo = bool(args.execute_demo)

    print("=" * 72)
    print("XAU Auto Trader - V51 Live-Safe Cycle")
    print("=" * 72)
    print("Mode: EXECUTE_DEMO" if execute_demo else "Mode: DRY_RUN")
    print(f"Config: {args.config}")
    print(f"Data path: {args.data_path}")
    print(f"Output dir: {args.output_dir}")
    print(f"Cycle log: {args.log_path}")

    result = run_v51_live_safe_cycle(
        config_path=args.config,
        output_dir=args.output_dir,
        data_path=args.data_path,
        log_path=args.log_path,
        execute_demo=execute_demo,
    )

    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print(f"Data update statuses: {', '.join(result.data_update_statuses) or 'n/a'}")
    print(f"CSV import statuses: {', '.join(result.csv_import_statuses) or 'n/a'}")
    print(f"Timeframe update status: {result.timeframe_update_status}")
    print(f"MTF context status: {result.mtf_context_status}")
    print(f"MTF final bias: {result.mtf_final_bias}")
    print(f"Freshness status: {result.freshness_status}")
    print(f"V51 called: {result.v51_called}")
    print(f"V51 status: {result.v51_status}")
    print(f"V51 accepted: {result.v51_accepted}")
    print("No real live execution is enabled.")


def _safe_call_results(label: str, fn: Callable[..., list[Any]], lines: list[str]) -> list[Any]:
    try:
        results = fn()
    except Exception as exc:
        lines.append(f"{label} ERROR {exc}")
        return [_SimpleStatus("ERROR", str(exc))]
    statuses = _result_statuses(results)
    lines.append(f"{label} statuses={','.join(statuses) or 'n/a'}")
    return results


def _safe_call_single(label: str, fn: Callable[..., Any], lines: list[str], **kwargs: Any) -> Any:
    try:
        result = fn(**kwargs)
    except Exception as exc:
        lines.append(f"{label} ERROR {exc}")
        return _SimpleStatus("ERROR", str(exc))
    status = str(getattr(result, "status", "UNKNOWN"))
    detail = f" final_bias={getattr(result, 'final_bias')}" if hasattr(result, "final_bias") else ""
    lines.append(f"{label} status={status}{detail}")
    return result


def _call_freshness(
    fn: Callable[..., Any],
    data_path: str | Path,
    now: pd.Timestamp | None,
    *,
    config: Any,
) -> Any:
    kwargs = {"symbol": "XAUUSD", "mt5_timestamp_timezone": getattr(config, "mt5_timestamp_timezone", "Europe/Rome")}
    if now is not None:
        kwargs["now"] = now
    return fn(data_path, **kwargs)


def _result_statuses(results: list[Any]) -> tuple[str, ...]:
    return tuple(str(getattr(result, "status", "UNKNOWN")) for result in results)


def _header(label: str) -> str:
    return f"================ {pd.Timestamp.now().isoformat()} {label} ================"


def _cycle_mode(execute_demo: bool) -> str:
    return "EXECUTE_DEMO" if execute_demo else "DRY_RUN"


def _append_csv(path: Path, row: dict[str, Any], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    if path.exists() and path.stat().st_size > 0:
        try:
            existing = pd.read_csv(path)
        except Exception:
            existing = pd.DataFrame(columns=columns)
        changed = False
        for column in columns:
            if column not in existing.columns:
                existing[column] = pd.NA
                changed = True
        if list(existing.columns) != columns:
            changed = True
        if changed:
            existing[columns].to_csv(path, index=False)
        write_header = False
    frame = pd.DataFrame([{column: row.get(column) for column in columns}], columns=columns)
    frame.to_csv(path, mode="a", header=write_header, index=False)


def _timestamp_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        return pd.Timestamp(value).isoformat()
    except Exception:
        return str(value)


def _local_timestamp_text(value: Any, timezone: str) -> str | None:
    if value is None or value == "":
        return None
    try:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(timezone)
        else:
            timestamp = timestamp.tz_convert(timezone)
        return timestamp.isoformat()
    except Exception:
        return None


def _utc_timestamp_text(value: Any, timezone: str) -> str | None:
    if value is None or value == "":
        return None
    try:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(timezone)
        else:
            timestamp = timestamp.tz_convert("UTC")
        return timestamp.tz_convert("UTC").isoformat()
    except Exception:
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value == "":
            continue
        return value
    return None


def _display(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    return str(value)


def _join_reasoning_list(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return " | ".join(str(item) for item in value if item)
    return str(value)


def _mtf_timeframe_summary_lines(mtf_context: Any | None) -> list[str]:
    summary_path = getattr(mtf_context, "summary_path", None)
    if summary_path is None:
        return []
    path = Path(summary_path)
    if not path.exists():
        return []
    try:
        summary = pd.read_csv(path)
    except Exception:
        return []
    if summary.empty or "timeframe" not in summary.columns:
        return []
    lines: list[str] = []
    for _, row in summary.iterrows():
        timeframe = row.get("timeframe", "")
        trend = row.get("trend_direction", row.get("status", ""))
        data_status = row.get("data_status", row.get("status", ""))
        used = row.get("used_in_bias", "")
        lines.append(f"{timeframe}: trend={trend}, data_status={data_status}, used_in_bias={used}")
    return lines


@dataclass(frozen=True)
class _SimpleStatus:
    status: str
    reason: str


if __name__ == "__main__":
    main()
