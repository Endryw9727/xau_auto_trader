"""Run a live-safe V51 demo cycle with data refresh and freshness gates."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Callable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

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
    "latest_closed_candle_time",
    "latest_closed_candle_age_minutes",
    "current_bid",
    "current_ask",
    "spread_points",
    "mtf_context_status",
    "mtf_final_bias",
    "mtf_filter_enabled",
    "mtf_filter_passed",
    "mtf_filter_reason",
    "v51_called",
    "v51_status",
    "v51_accepted",
    "signal_id",
    "side",
    "selected_candidate_time",
    "candidate_age_minutes",
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

    freshness = _call_freshness(freshness_fn, data_path, now)
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
        write_decision_audit(
            output_dir,
            mode=_cycle_mode(execute_demo),
            config=config,
            freshness=freshness,
            mtf_context=mtf_context,
            cycle_result=result,
            execution=None,
            dry_run=not execute_demo,
        )
        append_cycle_log(log_path, lines)
        return result

    execution = execution_fn(
        config_path=config_path,
        output_dir=output_dir,
        mtf_context_summary_path=getattr(mtf_context, "summary_path", None),
        dry_run=not execute_demo,
        **({"now": now} if now is not None else {}),
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
        dry_run=not execute_demo,
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
    dry_run: bool,
) -> dict[str, Any]:
    """Build one flat V51 cycle audit row from existing read-only telemetry."""
    latest_closed = _first_present(
        getattr(execution, "latest_closed_candle_time", None),
        getattr(freshness, "latest_timestamp", None),
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
        "latest_closed_candle_time": _timestamp_text(latest_closed),
        "latest_closed_candle_age_minutes": _float_or_none(getattr(freshness, "age_minutes", None)),
        "current_bid": _float_or_none(getattr(execution, "current_bid", None)),
        "current_ask": _float_or_none(getattr(execution, "current_ask", None)),
        "spread_points": _float_or_none(getattr(execution, "spread_points", None)),
        "mtf_context_status": cycle_result.mtf_context_status,
        "mtf_final_bias": None if mtf_final_bias is None else str(mtf_final_bias),
        "mtf_filter_enabled": mtf_filter_enabled,
        "mtf_filter_passed": mtf_filter_passed,
        "mtf_filter_reason": mtf_filter_reason,
        "v51_called": cycle_result.v51_called,
        "v51_status": cycle_result.v51_status,
        "v51_accepted": cycle_result.v51_accepted,
        "signal_id": getattr(execution, "signal_id", None),
        "side": getattr(execution, "side", None),
        "selected_candidate_time": _timestamp_text(getattr(execution, "selected_candidate_time", None)),
        "candidate_age_minutes": _float_or_none(getattr(execution, "candidate_age_minutes", None)),
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
    return "\n".join(lines) + "\n"


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


def _call_freshness(fn: Callable[..., Any], data_path: str | Path, now: pd.Timestamp | None) -> Any:
    kwargs = {"symbol": "XAUUSD"}
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
    frame = pd.DataFrame([{column: row.get(column) for column in columns}], columns=columns)
    frame.to_csv(path, mode="a", header=not path.exists(), index=False)


def _timestamp_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        return pd.Timestamp(value).isoformat()
    except Exception:
        return str(value)


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
