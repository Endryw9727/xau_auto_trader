"""Build a V51 diagnostic report from local OHLCV CSV data."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_feed.market_data import load_csv_data
from src.strategy_lab.strategy_v51_demo_intraday import (
    DEFAULT_V51_CONFIG_PATH,
    V51DemoIntradayConfig,
    build_demo_intraday_decision_log,
    load_v51_config,
)
from src.utils.time_alignment import align_timestamp, to_utc_timestamp


DEFAULT_V51_DIAGNOSTIC_OUTPUT_DIR = Path("reports/diagnostics")
DEFAULT_V51_DIAGNOSTIC_SUMMARY = "v51_diagnostic_summary.csv"
DEFAULT_V51_DIAGNOSTIC_REJECTIONS = "v51_diagnostic_rejections.csv"
DEFAULT_V51_DIAGNOSTIC_LATEST = "v51_diagnostic_latest.txt"
DEFAULT_V51_LIVE_CANDIDATE_PROBE = "v51_live_candidate_probe.csv"
DEFAULT_V51_LIVE_CANDIDATE_PROBE_LATEST = "v51_live_candidate_probe_latest.txt"
DEFAULT_XAUUSD_CSV_PATH = Path("data/raw/xauusd.csv")

SUMMARY_COLUMNS = [
    "generated_at",
    "status",
    "reason",
    "config_path",
    "csv_path",
    "requested_candles",
    "candles_loaded",
    "candles_analyzed",
    "latest_candle_time",
    "candidate_count",
    "buy_candidates",
    "sell_candidates",
    "accepted_candidates",
    "rejected_candidates",
    "top_rejection_reasons",
    "market_sessions",
    "dominant_session",
    "average_spread_cost",
    "average_slippage_estimate",
    "average_score",
    "average_rr",
]

REJECTION_COLUMNS = [
    "signal_id",
    "candle_time",
    "session",
    "side",
    "decision",
    "score",
    "score_gap",
    "risk_reward",
    "spread_cost",
    "slippage_estimate",
    "reason",
]

PROBE_COLUMNS = [
    "generated_at",
    "primary_csv_path",
    "rows_loaded",
    "latest_data_time_raw",
    "latest_data_time_utc",
    "latest_closed_candle_time_expected",
    "latest_closed_candle_time_used",
    "candidates_generated_last_100",
    "candidates_generated_last_20",
    "nearest_candidate_before_latest",
    "nearest_candidate_after_latest",
    "selected_candidate_time",
    "selected_candidate_age_minutes",
    "rejection_reason",
    "latest_candle_had_candidate",
    "latest_candle_decision",
    "latest_candle_reason",
]


@dataclass(frozen=True)
class V51DiagnosticReportResult:
    """Paths and status for one generated V51 diagnostic report."""

    status: str
    reason: str
    summary_path: Path
    rejections_path: Path
    latest_path: Path
    probe_path: Path
    probe_latest_path: Path


def run_v51_diagnostic_report(
    *,
    candles: int = 200,
    config_path: str | Path = DEFAULT_V51_CONFIG_PATH,
    csv_path: str | Path = DEFAULT_XAUUSD_CSV_PATH,
    output_dir: str | Path = DEFAULT_V51_DIAGNOSTIC_OUTPUT_DIR,
) -> V51DiagnosticReportResult:
    """Generate V51 diagnostics without touching execution or broker code."""
    if candles <= 0:
        raise ValueError("candles must be positive")

    paths = diagnostic_paths(output_dir)
    config_path = Path(config_path)
    csv_path = Path(csv_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        config = load_v51_config(config_path)
        data = load_csv_data(csv_path)
    except Exception as exc:
        reason = str(exc)
        _write_error_reports(paths, config_path, csv_path, candles, status="ERROR", reason=reason)
        return V51DiagnosticReportResult(
            "ERROR",
            reason,
            paths["summary"],
            paths["rejections"],
            paths["latest"],
            paths["probe"],
            paths["probe_latest"],
        )

    required_rows = config.warmup_candles + 1
    if len(data) < required_rows:
        reason = f"dataset insufficient: rows={len(data)}, required_min_rows={required_rows}"
        _write_error_reports(
            paths,
            config_path,
            csv_path,
            candles,
            status="INSUFFICIENT_DATA",
            reason=reason,
            candles_loaded=len(data),
        )
        return V51DiagnosticReportResult(
            "INSUFFICIENT_DATA",
            reason,
            paths["summary"],
            paths["rejections"],
            paths["latest"],
            paths["probe"],
            paths["probe_latest"],
        )

    working_data = data.tail(config.warmup_candles + candles).copy()
    decision_log = build_demo_intraday_decision_log(working_data, config, enforce_daily_limit=False)
    decision_log = _latest_decisions(decision_log, candles)
    latest_data_time = _latest_data_timestamp(data)
    summary = build_diagnostic_summary(
        decision_log,
        config,
        config_path=config_path,
        csv_path=csv_path,
        requested_candles=candles,
        candles_loaded=len(data),
        latest_data_time=latest_data_time,
    )
    rejections = build_rejections_report(decision_log)
    probe = build_live_candidate_probe(decision_log, config, csv_path=csv_path, rows_loaded=len(data), latest_data_time=latest_data_time)
    latest_text = build_latest_text(summary.iloc[0].to_dict(), decision_log, probe.iloc[0].to_dict())
    probe_latest_text = build_probe_latest_text(probe.iloc[0].to_dict())

    summary.to_csv(paths["summary"], index=False)
    rejections.to_csv(paths["rejections"], index=False)
    probe.to_csv(paths["probe"], index=False)
    paths["latest"].write_text(latest_text, encoding="utf-8")
    paths["probe_latest"].write_text(probe_latest_text, encoding="utf-8")
    return V51DiagnosticReportResult(
        "OK",
        "V51 diagnostic report generated",
        paths["summary"],
        paths["rejections"],
        paths["latest"],
        paths["probe"],
        paths["probe_latest"],
    )


def build_diagnostic_summary(
    decision_log: pd.DataFrame,
    config: V51DemoIntradayConfig,
    *,
    config_path: Path,
    csv_path: Path,
    requested_candles: int,
    candles_loaded: int,
    latest_data_time: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Return a one-row summary for the V51 diagnostic report."""
    candidates = _candidate_rows(decision_log)
    accepted = candidates[candidates["decision"] == "ACCEPTED"] if not candidates.empty else candidates
    rejected = candidates[candidates["decision"] != "ACCEPTED"] if not candidates.empty else candidates
    sessions = decision_log["session"].astype(str) if "session" in decision_log.columns and not decision_log.empty else pd.Series(dtype=str)
    latest = latest_data_time or _latest_timestamp(decision_log)
    row = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "status": "OK",
        "reason": "V51 diagnostic report generated",
        "config_path": str(config_path),
        "csv_path": str(csv_path),
        "requested_candles": int(requested_candles),
        "candles_loaded": int(candles_loaded),
        "candles_analyzed": int(len(decision_log)),
        "latest_candle_time": latest.isoformat() if latest is not None else "",
        "candidate_count": int(len(candidates)),
        "buy_candidates": int((candidates["side"] == "BUY").sum()) if not candidates.empty else 0,
        "sell_candidates": int((candidates["side"] == "SELL").sum()) if not candidates.empty else 0,
        "accepted_candidates": int(len(accepted)),
        "rejected_candidates": int(len(rejected)),
        "top_rejection_reasons": top_rejection_reasons(rejected),
        "market_sessions": "; ".join(sessions.value_counts().index.tolist()[:5]) if not sessions.empty else "",
        "dominant_session": str(sessions.value_counts().index[0]) if not sessions.empty else "",
        "average_spread_cost": _mean_numeric(candidates.get("spread_cost")) if not candidates.empty else float(config.spread_cost),
        "average_slippage_estimate": _mean_numeric(candidates.get("slippage_estimate")) if not candidates.empty else float(config.slippage_estimate),
        "average_score": _mean_numeric(candidates.get("score")),
        "average_rr": _mean_numeric(candidates.get("risk_reward")),
    }
    return pd.DataFrame([row], columns=SUMMARY_COLUMNS)


def build_rejections_report(decision_log: pd.DataFrame) -> pd.DataFrame:
    """Return rejected V51 candidate rows with complete reasons."""
    candidates = _candidate_rows(decision_log)
    if candidates.empty:
        return pd.DataFrame(columns=REJECTION_COLUMNS)
    rejected = candidates[candidates["decision"] != "ACCEPTED"].copy()
    return rejected[REJECTION_COLUMNS].reset_index(drop=True)


def top_rejection_reasons(rejected: pd.DataFrame, *, limit: int = 5) -> str:
    """Format the most frequent rejection reasons."""
    if rejected.empty or "reason" not in rejected.columns:
        return ""
    counts = rejected["reason"].astype(str).value_counts().head(limit)
    return "; ".join(f"{reason} ({count})" for reason, count in counts.items())


def build_latest_text(summary_row: dict[str, Any], decision_log: pd.DataFrame, probe_row: dict[str, Any] | None = None) -> str:
    """Build a compact human-readable latest-candidate diagnostic."""
    candidates = _recent_candidates_for_latest_text(_candidate_rows(decision_log), summary_row).tail(10)
    lines = [
        "V51 Diagnostic Report",
        "=" * 72,
        f"Status: {summary_row.get('status')}",
        f"Reason: {summary_row.get('reason')}",
        f"Latest candle time: {summary_row.get('latest_candle_time')}",
        f"Candles analyzed: {summary_row.get('candles_analyzed')}",
        f"Candidates: {summary_row.get('candidate_count')}",
        f"BUY candidates: {summary_row.get('buy_candidates')}",
        f"SELL candidates: {summary_row.get('sell_candidates')}",
        f"Accepted candidates: {summary_row.get('accepted_candidates')}",
        f"Rejected candidates: {summary_row.get('rejected_candidates')}",
        f"Top rejection reasons: {summary_row.get('top_rejection_reasons')}",
        f"Market sessions: {summary_row.get('market_sessions')}",
        f"Average spread cost: {summary_row.get('average_spread_cost')}",
        f"Slippage estimate: {summary_row.get('average_slippage_estimate')}",
        f"Average score: {summary_row.get('average_score')}",
        f"Average RR: {summary_row.get('average_rr')}",
        "",
        "Live candidate probe",
        "-" * 72,
        f"Latest candle had candidate: {(probe_row or {}).get('latest_candle_had_candidate', '')}",
        f"Selected candidate time: {(probe_row or {}).get('selected_candidate_time', '')}",
        f"Rejection reason: {(probe_row or {}).get('rejection_reason', '')}",
        f"Candidates last 100: {(probe_row or {}).get('candidates_generated_last_100', '')}",
        f"Candidates last 20: {(probe_row or {}).get('candidates_generated_last_20', '')}",
        "",
        "Last 10 candidates",
        "-" * 72,
    ]
    if candidates.empty:
        lines.append("No BUY/SELL candidates found.")
    for _, row in candidates.iterrows():
        lines.append(
            f"{row['candle_time']} | {row['session']} | {row['side']} | "
            f"{row['decision']} | score={row['score']} | RR={row['risk_reward']} | reason={row['reason']}"
        )
    lines.append("")
    lines.append("No orders were sent. This is diagnostics only.")
    return "\n".join(lines) + "\n"


def build_live_candidate_probe(
    decision_log: pd.DataFrame,
    config: V51DemoIntradayConfig,
    *,
    csv_path: Path,
    rows_loaded: int,
    latest_data_time: pd.Timestamp | None,
) -> pd.DataFrame:
    """Build a one-row live-candidate visibility probe from local diagnostics only."""
    timezone = config.mt5_timestamp_timezone
    prepared = _decision_log_with_utc(decision_log, timezone)
    latest_snapshot = align_timestamp(latest_data_time, source_timezone=timezone)
    latest_utc = latest_snapshot.utc
    candidates = _candidate_rows(prepared)
    latest_row = _row_at_time(prepared, latest_utc)
    candidates_last_100 = _candidate_count_in_tail(prepared, 100)
    candidates_last_20 = _candidate_count_in_tail(prepared, 20)
    nearest_before = _nearest_candidate(candidates, latest_utc, direction="before")
    nearest_after = _nearest_candidate(candidates, latest_utc, direction="after")
    latest_had_candidate = bool(
        latest_row is not None
        and str(latest_row.get("side", "")).upper() in {"BUY", "SELL"}
    )
    selected_candidate_time = ""
    selected_candidate_age = None
    if latest_had_candidate and str(latest_row.get("decision", "")).upper() == "ACCEPTED":
        selected_candidate_time = _iso_or_empty(latest_row.get("candle_time_utc"))
        if latest_utc is not None and latest_row.get("candle_time_utc") is not None:
            selected_candidate_age = (latest_utc - latest_row["candle_time_utc"]).total_seconds() / 60.0
    rejection_reason = _probe_rejection_reason(
        latest_row,
        latest_utc=latest_utc,
        nearest_before=nearest_before,
        nearest_after=nearest_after,
    )
    row = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "primary_csv_path": str(csv_path),
        "rows_loaded": int(rows_loaded),
        "latest_data_time_raw": latest_snapshot.raw,
        "latest_data_time_utc": latest_snapshot.utc_iso,
        "latest_closed_candle_time_expected": latest_snapshot.utc_iso,
        "latest_closed_candle_time_used": _iso_or_empty(_latest_timestamp_utc(prepared)),
        "candidates_generated_last_100": int(candidates_last_100),
        "candidates_generated_last_20": int(candidates_last_20),
        "nearest_candidate_before_latest": _candidate_summary(nearest_before),
        "nearest_candidate_after_latest": _candidate_summary(nearest_after),
        "selected_candidate_time": selected_candidate_time,
        "selected_candidate_age_minutes": selected_candidate_age,
        "rejection_reason": rejection_reason,
        "latest_candle_had_candidate": latest_had_candidate,
        "latest_candle_decision": "" if latest_row is None else str(latest_row.get("decision", "")),
        "latest_candle_reason": "" if latest_row is None else str(latest_row.get("reason", "")),
    }
    return pd.DataFrame([row], columns=PROBE_COLUMNS)


def build_probe_latest_text(row: dict[str, Any]) -> str:
    """Build the human-readable live candidate probe report."""
    lines = [
        "V51 Live Candidate Probe",
        "=" * 72,
        f"Primary CSV path: {row.get('primary_csv_path')}",
        f"Rows loaded: {row.get('rows_loaded')}",
        f"Latest data time raw: {row.get('latest_data_time_raw')}",
        f"Latest data time UTC: {row.get('latest_data_time_utc')}",
        f"Latest closed candle expected: {row.get('latest_closed_candle_time_expected')}",
        f"Latest closed candle used: {row.get('latest_closed_candle_time_used')}",
        f"Candidates generated last 100: {row.get('candidates_generated_last_100')}",
        f"Candidates generated last 20: {row.get('candidates_generated_last_20')}",
        f"Nearest candidate before latest: {row.get('nearest_candidate_before_latest') or 'n/a'}",
        f"Nearest candidate after latest: {row.get('nearest_candidate_after_latest') or 'n/a'} (diagnostic only, never tradable)",
        f"Selected candidate time: {row.get('selected_candidate_time') or 'n/a'}",
        f"Selected candidate age minutes: {row.get('selected_candidate_age_minutes')}",
        f"Latest candle had candidate: {row.get('latest_candle_had_candidate')}",
        f"Latest candle decision: {row.get('latest_candle_decision')}",
        f"Latest candle reason: {row.get('latest_candle_reason')}",
        f"Rejection reason: {row.get('rejection_reason')}",
        "",
        "No orders were sent. This is diagnostics only.",
    ]
    return "\n".join(lines) + "\n"


def diagnostic_paths(output_dir: str | Path = DEFAULT_V51_DIAGNOSTIC_OUTPUT_DIR) -> dict[str, Path]:
    """Return output paths for the V51 diagnostic report."""
    directory = Path(output_dir)
    return {
        "summary": directory / DEFAULT_V51_DIAGNOSTIC_SUMMARY,
        "rejections": directory / DEFAULT_V51_DIAGNOSTIC_REJECTIONS,
        "latest": directory / DEFAULT_V51_DIAGNOSTIC_LATEST,
        "probe": directory / DEFAULT_V51_LIVE_CANDIDATE_PROBE,
        "probe_latest": directory / DEFAULT_V51_LIVE_CANDIDATE_PROBE_LATEST,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candles", type=int, default=200, help="Latest closed candles to diagnose.")
    parser.add_argument("--config", type=Path, default=DEFAULT_V51_CONFIG_PATH, help="V51 config path.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_XAUUSD_CSV_PATH, help="Local OHLCV CSV path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_V51_DIAGNOSTIC_OUTPUT_DIR, help="Report output directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_v51_diagnostic_report(
        candles=args.candles,
        config_path=args.config,
        csv_path=args.csv,
        output_dir=args.output_dir,
    )
    print("=" * 72)
    print("XAU Auto Trader - V51 Diagnostic Report")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print(f"Summary: {result.summary_path}")
    print(f"Rejections: {result.rejections_path}")
    print(f"Latest: {result.latest_path}")
    print(f"Live candidate probe: {result.probe_path}")
    print(f"Live candidate probe latest: {result.probe_latest_path}")
    print("No orders were sent. This is diagnostics only.")


def _latest_decisions(decision_log: pd.DataFrame, candles: int) -> pd.DataFrame:
    if decision_log.empty:
        return decision_log.copy()
    prepared = decision_log.copy()
    prepared["candle_time_dt"] = pd.to_datetime(prepared["candle_time"], errors="coerce")
    prepared = prepared.sort_values("candle_time_dt").tail(candles).drop(columns=["candle_time_dt"])
    return prepared.reset_index(drop=True)


def _candidate_rows(decision_log: pd.DataFrame) -> pd.DataFrame:
    if decision_log.empty:
        return pd.DataFrame(columns=REJECTION_COLUMNS)
    candidates = decision_log[decision_log["side"].astype(str).isin(["BUY", "SELL"])].copy()
    for column in REJECTION_COLUMNS:
        if column not in candidates.columns:
            candidates[column] = pd.NA
    return candidates


def _latest_data_timestamp(data: pd.DataFrame) -> pd.Timestamp | None:
    if data is None or data.empty or not isinstance(data.index, pd.DatetimeIndex):
        return None
    return pd.Timestamp(data.index[-1])


def _latest_timestamp(decision_log: pd.DataFrame) -> pd.Timestamp | None:
    if decision_log.empty or "candle_time" not in decision_log.columns:
        return None
    times = pd.to_datetime(decision_log["candle_time"], errors="coerce").dropna()
    if times.empty:
        return None
    return pd.Timestamp(times.max())


def _latest_timestamp_utc(decision_log: pd.DataFrame) -> pd.Timestamp | None:
    if decision_log.empty:
        return None
    if "candle_time_utc" in decision_log.columns:
        values = pd.Series(decision_log["candle_time_utc"]).dropna()
        if values.empty:
            return None
        return pd.Timestamp(values.max()).tz_convert("UTC")
    latest = _latest_timestamp(decision_log)
    return to_utc_timestamp(latest, source_timezone="UTC") if latest is not None else None


def _decision_log_with_utc(decision_log: pd.DataFrame, timezone: str) -> pd.DataFrame:
    prepared = decision_log.copy()
    if prepared.empty:
        prepared["candle_time_utc"] = pd.Series(dtype="datetime64[ns, UTC]")
        return prepared
    prepared["candle_time_utc"] = pd.Series(
        [to_utc_timestamp(value, source_timezone=timezone) for value in prepared["candle_time"]],
        index=prepared.index,
        dtype="datetime64[ns, UTC]",
    )
    return prepared


def _row_at_time(decision_log: pd.DataFrame, timestamp_utc: pd.Timestamp | None) -> pd.Series | None:
    if timestamp_utc is None or decision_log.empty or "candle_time_utc" not in decision_log.columns:
        return None
    rows = decision_log[decision_log["candle_time_utc"] == timestamp_utc]
    if rows.empty:
        return None
    return rows.iloc[-1]


def _candidate_count_in_tail(decision_log: pd.DataFrame, candles: int) -> int:
    if decision_log.empty:
        return 0
    return int(len(_candidate_rows(decision_log.tail(candles))))


def _nearest_candidate(candidates: pd.DataFrame, latest_utc: pd.Timestamp | None, *, direction: str) -> pd.Series | None:
    if latest_utc is None or candidates.empty or "candle_time_utc" not in candidates.columns:
        return None
    valid = candidates.dropna(subset=["candle_time_utc"]).copy()
    if valid.empty:
        return None
    if direction == "before":
        valid = valid[valid["candle_time_utc"] <= latest_utc].sort_values("candle_time_utc")
        return None if valid.empty else valid.iloc[-1]
    valid = valid[valid["candle_time_utc"] > latest_utc].sort_values("candle_time_utc")
    return None if valid.empty else valid.iloc[0]


def _probe_rejection_reason(
    latest_row: pd.Series | None,
    *,
    latest_utc: pd.Timestamp | None,
    nearest_before: pd.Series | None,
    nearest_after: pd.Series | None,
) -> str:
    if nearest_after is not None:
        future = _candidate_summary(nearest_after)
        if latest_row is None:
            return f"candidate future rejected: nearest_candidate_after_latest={future}"
    if latest_row is None:
        if nearest_before is not None:
            return f"time mismatch: latest closed candle missing from decision log; candidate generated but not latest: { _candidate_summary(nearest_before) }"
        return "time mismatch: latest closed candle missing from decision log"

    side = str(latest_row.get("side", "")).upper()
    decision = str(latest_row.get("decision", "")).upper()
    reason = str(latest_row.get("reason", "")).strip()
    if side not in {"BUY", "SELL"}:
        suffix = f"; candidate generated but not latest: {_candidate_summary(nearest_before)}" if nearest_before is not None else ""
        return f"no setup: {reason or 'latest candle has no BUY/SELL side'}{suffix}"
    if decision == "ACCEPTED":
        return "latest candle candidate accepted"
    lower = reason.lower()
    if "session blocked" in lower:
        return f"session blocked: {reason}"
    if "score" in lower:
        return f"score below threshold: {reason}" if "below" in lower else reason
    if "quality guard" in lower:
        return f"quality guard: {reason}"
    if "setup" in lower:
        return f"quality guard: {reason}" if "not confirmed" in lower else f"no setup: {reason}"
    if latest_utc is not None and latest_row.get("candle_time_utc") is not None and latest_row["candle_time_utc"] > latest_utc:
        return f"candidate future rejected: {_candidate_summary(latest_row)}"
    return reason or "candidate generated but not accepted"


def _candidate_summary(row: pd.Series | None) -> str:
    if row is None:
        return ""
    return (
        f"{row.get('signal_id', '')}|{_iso_or_empty(row.get('candle_time_utc'))}|"
        f"{row.get('side', '')}|{row.get('decision', '')}|"
        f"score={row.get('score', '')}|reason={row.get('reason', '')}"
    )


def _iso_or_empty(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert("UTC")
        return timestamp.isoformat()
    except Exception:
        return str(value)


def _recent_candidates_for_latest_text(candidates: pd.DataFrame, summary_row: dict[str, Any]) -> pd.DataFrame:
    if candidates.empty:
        return candidates
    latest_text = summary_row.get("latest_candle_time")
    try:
        latest = pd.Timestamp(latest_text)
    except Exception:
        return candidates
    requested = int(summary_row.get("requested_candles") or 200)
    window_start = latest - pd.Timedelta(minutes=max(requested, 1) * 15)
    prepared = candidates.copy()
    prepared["candle_time_dt"] = pd.to_datetime(prepared["candle_time"], errors="coerce")
    filtered = prepared[prepared["candle_time_dt"] >= window_start]
    if filtered.empty:
        return candidates.iloc[0:0]
    return filtered.drop(columns=["candle_time_dt"])


def _mean_numeric(series: pd.Series | None) -> float:
    if series is None:
        return 0.0
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else 0.0


def _write_error_reports(
    paths: dict[str, Path],
    config_path: Path,
    csv_path: Path,
    candles: int,
    *,
    status: str,
    reason: str,
    candles_loaded: int = 0,
) -> None:
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(
        [
            {
                "generated_at": pd.Timestamp.now().isoformat(),
                "status": status,
                "reason": reason,
                "config_path": str(config_path),
                "csv_path": str(csv_path),
                "requested_candles": int(candles),
                "candles_loaded": int(candles_loaded),
                "candles_analyzed": 0,
                "latest_candle_time": "",
                "candidate_count": 0,
                "buy_candidates": 0,
                "sell_candidates": 0,
                "accepted_candidates": 0,
                "rejected_candidates": 0,
                "top_rejection_reasons": "",
                "market_sessions": "",
                "dominant_session": "",
                "average_spread_cost": 0.0,
                "average_slippage_estimate": 0.0,
                "average_score": 0.0,
                "average_rr": 0.0,
            }
        ],
        columns=SUMMARY_COLUMNS,
    )
    summary.to_csv(paths["summary"], index=False)
    pd.DataFrame(columns=REJECTION_COLUMNS).to_csv(paths["rejections"], index=False)
    probe = pd.DataFrame(
        [
            {
                "generated_at": pd.Timestamp.now().isoformat(),
                "primary_csv_path": str(csv_path),
                "rows_loaded": int(candles_loaded),
                "latest_data_time_raw": "",
                "latest_data_time_utc": "",
                "latest_closed_candle_time_expected": "",
                "latest_closed_candle_time_used": "",
                "candidates_generated_last_100": 0,
                "candidates_generated_last_20": 0,
                "nearest_candidate_before_latest": "",
                "nearest_candidate_after_latest": "",
                "selected_candidate_time": "",
                "selected_candidate_age_minutes": None,
                "rejection_reason": reason,
                "latest_candle_had_candidate": False,
                "latest_candle_decision": "",
                "latest_candle_reason": "",
            }
        ],
        columns=PROBE_COLUMNS,
    )
    probe.to_csv(paths["probe"], index=False)
    paths["latest"].write_text(
        "\n".join(
            [
                "V51 Diagnostic Report",
                "=" * 72,
                f"Status: {status}",
                f"Reason: {reason}",
                "No orders were sent. This is diagnostics only.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    paths["probe_latest"].write_text(build_probe_latest_text(probe.iloc[0].to_dict()), encoding="utf-8")


if __name__ == "__main__":
    main()
