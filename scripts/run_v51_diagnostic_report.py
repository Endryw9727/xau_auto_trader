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
from src.strategy_lab import strategy_v50_pine
from src.utils.time_alignment import align_timestamp, to_utc_timestamp


DEFAULT_V51_DIAGNOSTIC_OUTPUT_DIR = Path("reports/diagnostics")
DEFAULT_V51_DIAGNOSTIC_SUMMARY = "v51_diagnostic_summary.csv"
DEFAULT_V51_DIAGNOSTIC_REJECTIONS = "v51_diagnostic_rejections.csv"
DEFAULT_V51_DIAGNOSTIC_LATEST = "v51_diagnostic_latest.txt"
DEFAULT_V51_LIVE_CANDIDATE_PROBE = "v51_live_candidate_probe.csv"
DEFAULT_V51_LIVE_CANDIDATE_PROBE_LATEST = "v51_live_candidate_probe_latest.txt"
DEFAULT_V51_SESSION_BEHAVIOR_LATEST = "v51_session_behavior_latest.txt"
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
    "setup_score",
    "context_bias",
    "quality_guard_decision",
    "execution_decision",
    "final_reason",
    "guard_category",
    "score_breakdown",
    "score_breakdown_total",
    "high_score_explanation",
    "htf_bias_direction",
    "candidate_side",
    "countertrend",
    "m15_state",
    "m5_m1_timing",
    "sweep_reclaim_present",
    "displacement_present",
    "quality_guard_detail",
    "asia_shadow_classification",
    "asia_execution_mode",
    "asia_range_high",
    "asia_range_low",
    "asia_swept_high",
    "asia_swept_low",
    "london_manipulation_detected",
    "ny_reversal_candidate",
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
    session_behavior_latest_path: Path


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
            paths["session_behavior_latest"],
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
            paths["session_behavior_latest"],
        )

    working_data = data.tail(config.warmup_candles + candles).copy()
    decision_log = build_demo_intraday_decision_log(working_data, config, enforce_daily_limit=False)
    decision_log = _latest_decisions(decision_log, candles)
    features = _build_v51_diagnostic_features(working_data)
    decision_log = enrich_decision_log_for_diagnostics(decision_log, features, config)
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
    session_behavior_text = build_session_behavior_latest_text(decision_log)

    summary.to_csv(paths["summary"], index=False)
    rejections.to_csv(paths["rejections"], index=False)
    probe.to_csv(paths["probe"], index=False)
    paths["latest"].write_text(latest_text, encoding="utf-8")
    paths["probe_latest"].write_text(probe_latest_text, encoding="utf-8")
    paths["session_behavior_latest"].write_text(session_behavior_text, encoding="utf-8")
    return V51DiagnosticReportResult(
        "OK",
        "V51 diagnostic report generated",
        paths["summary"],
        paths["rejections"],
        paths["latest"],
        paths["probe"],
        paths["probe_latest"],
        paths["session_behavior_latest"],
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


def enrich_decision_log_for_diagnostics(
    decision_log: pd.DataFrame,
    features: pd.DataFrame,
    config: V51DemoIntradayConfig,
) -> pd.DataFrame:
    """Add report-only V51 diagnostic columns to a decision log."""
    if decision_log.empty:
        return _ensure_diagnostic_columns(decision_log.copy())

    enriched = decision_log.copy()
    feature_lookup = _feature_lookup_by_time(features)
    merged_rows: list[dict[str, Any]] = []
    for _, row in enriched.iterrows():
        feature_row = _feature_row_for_decision(row, feature_lookup)
        merged = row.copy()
        if feature_row is not None:
            for column, value in feature_row.items():
                if column not in merged.index:
                    merged[column] = value
        merged_rows.append(dict(merged))
    working = pd.DataFrame(merged_rows, index=enriched.index)
    working = _add_asia_liquidity_context(working)
    diagnostics: list[dict[str, Any]] = []
    for _, row in working.iterrows():
        diagnostics.append(_diagnostics_for_row(row, config))
    diagnostic_frame = pd.DataFrame(diagnostics, index=enriched.index)
    for column in diagnostic_frame.columns:
        enriched[column] = diagnostic_frame[column]
    return _ensure_diagnostic_columns(enriched)


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
        "High-score rejected candidates (score >= 60)",
        "-" * 72,
    ]
    high_score_lines = _high_score_rejection_lines(_candidate_rows(decision_log))
    lines.extend(high_score_lines if high_score_lines else ["No high-score rejected candidates in analyzed window."])
    lines.extend(
        [
            "",
            "Last 10 candidates",
            "-" * 72,
        ]
    )
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


def build_session_behavior_latest_text(decision_log: pd.DataFrame) -> str:
    """Build per-session candidate behavior diagnostics."""
    candidates = _candidate_rows(decision_log)
    lines = [
        "V51 Session Behavior",
        "=" * 72,
        "This is diagnostics only. Asia classifications are shadow context and never direct execution.",
        "",
    ]
    if candidates.empty:
        lines.append("No BUY/SELL candidates found.")
        return "\n".join(lines) + "\n"

    for session, group in candidates.groupby(candidates["session"].astype(str), dropna=False):
        accepted = group[group["decision"] == "ACCEPTED"]
        rejected = group[group["decision"] != "ACCEPTED"]
        side_counts = group["side"].astype(str).value_counts()
        lines.extend(
            [
                f"Session: {session}",
                f"- candidates: {len(group)}",
                f"- accepted: {len(accepted)}",
                f"- rejected: {len(rejected)}",
                f"- avg score: {_mean_numeric(group.get('score')):.2f}",
                f"- avg RR: {_mean_numeric(group.get('risk_reward')):.2f}",
                f"- top rejection reasons: {top_rejection_reasons(rejected) or 'n/a'}",
                f"- BUY/SELL distribution: BUY={int(side_counts.get('BUY', 0))}, SELL={int(side_counts.get('SELL', 0))}",
            ]
        )
        if str(session).upper() in {"ASIA", "ASIA/LONDON"}:
            classes = group["asia_shadow_classification"].astype(str).value_counts()
            class_text = ", ".join(f"{name}={count}" for name, count in classes.items() if name and name != "nan")
            asia_high = _last_non_empty(group.get("asia_range_high"))
            asia_low = _last_non_empty(group.get("asia_range_low"))
            lines.append(f"- Asia shadow classifications: {class_text or 'n/a'}")
            lines.append(f"- Asia range high: {asia_high}")
            lines.append(f"- Asia range low: {asia_low}")
            lines.append(f"- Asia swept high: {int(_bool_series_sum(group.get('asia_swept_high')))}")
            lines.append(f"- Asia swept low: {int(_bool_series_sum(group.get('asia_swept_low')))}")
            lines.append(f"- London manipulation detected: {int(_bool_series_sum(group.get('london_manipulation_detected')))}")
            lines.append("- Asia execution mode: SHADOW_ONLY/REPORT_ONLY")
        if str(session).upper() == "NEW YORK":
            lines.append(f"- NY reversal candidates after Asia sweep: {int(_bool_series_sum(group.get('ny_reversal_candidate')))}")
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
        "session_behavior_latest": directory / DEFAULT_V51_SESSION_BEHAVIOR_LATEST,
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
    print(f"Session behavior latest: {result.session_behavior_latest_path}")
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


def _build_v51_diagnostic_features(market_data: pd.DataFrame) -> pd.DataFrame:
    if strategy_v50_pine.V50_REQUIRED_COLUMNS.issubset(market_data.columns):
        return market_data.copy()
    return strategy_v50_pine.build_v50_features(market_data)


def _feature_lookup_by_time(features: pd.DataFrame) -> dict[pd.Timestamp, pd.Series]:
    if features.empty or not isinstance(features.index, pd.DatetimeIndex):
        return {}
    return {pd.Timestamp(index).tz_localize(None): row for index, row in features.iterrows()}


def _feature_row_for_decision(row: pd.Series, feature_lookup: dict[pd.Timestamp, pd.Series]) -> pd.Series | None:
    try:
        timestamp = pd.Timestamp(row.get("candle_time")).tz_localize(None)
    except Exception:
        return None
    return feature_lookup.get(timestamp)


def _add_asia_liquidity_context(decision_log: pd.DataFrame) -> pd.DataFrame:
    """Attach report-only Asia range and sweep context without changing decisions."""
    result = decision_log.copy()
    context_columns = {
        "asia_range_high": pd.NA,
        "asia_range_low": pd.NA,
        "asia_swept_high": False,
        "asia_swept_low": False,
        "london_manipulation_detected": False,
        "ny_reversal_candidate": False,
    }
    for column, default in context_columns.items():
        if column not in result.columns:
            result[column] = default
    if result.empty or "candle_time" not in result.columns:
        return result

    result["_diagnostic_candle_time"] = [_naive_timestamp(value) for value in result["candle_time"]]
    result["_diagnostic_trade_date"] = [
        timestamp.date() if not pd.isna(timestamp) else None for timestamp in result["_diagnostic_candle_time"]
    ]

    sweep_sessions = {"ASIA/LONDON", "LONDON", "LONDON/US"}
    for trade_date, group in result.groupby("_diagnostic_trade_date", dropna=True):
        if trade_date is None:
            continue
        asia_high: float | None = None
        asia_low: float | None = None
        london_swept_high = False
        london_swept_low = False
        sorted_group = group.sort_values("_diagnostic_candle_time")
        for index, row in sorted_group.iterrows():
            session = str(row.get("session", "")).upper()
            high = _numeric(row.get("High"))
            low = _numeric(row.get("Low"))
            close = _numeric(row.get("Close"))

            if session == "ASIA":
                asia_high = high if asia_high is None else max(asia_high, high)
                asia_low = low if asia_low is None else min(asia_low, low)

            if asia_high is not None and asia_low is not None:
                result.at[index, "asia_range_high"] = asia_high
                result.at[index, "asia_range_low"] = asia_low
                swept_high = session in sweep_sessions and high > asia_high
                swept_low = session in sweep_sessions and low < asia_low
                manipulation = bool(swept_high or swept_low)
                result.at[index, "asia_swept_high"] = bool(swept_high)
                result.at[index, "asia_swept_low"] = bool(swept_low)
                result.at[index, "london_manipulation_detected"] = bool(manipulation)
                side = str(row.get("side", "")).upper()
                ny_reversal = session == "NEW YORK" and (
                    (side == "SELL" and london_swept_high)
                    or (side == "BUY" and london_swept_low)
                    or (side == "" and (london_swept_high or london_swept_low))
                )
                result.at[index, "ny_reversal_candidate"] = bool(ny_reversal)

                if manipulation:
                    london_swept_high = london_swept_high or bool(swept_high and close <= asia_high)
                    london_swept_low = london_swept_low or bool(swept_low and close >= asia_low)

    return result.drop(columns=["_diagnostic_candle_time", "_diagnostic_trade_date"], errors="ignore")


def _diagnostics_for_row(row: pd.Series, config: V51DemoIntradayConfig) -> dict[str, Any]:
    side = str(row.get("side", "")).upper()
    score = _numeric(row.get("score"))
    context_bias = _context_bias(row)
    quality_decision = _quality_guard_decision(row, side)
    breakdown, total, positive = _score_breakdown(row, side)
    final_reason = _diagnostic_final_reason(row, config)
    asia_class = _asia_shadow_classification(row)
    asia_execution_mode = _asia_execution_mode(row, config)
    return {
        "setup_score": score,
        "context_bias": context_bias,
        "quality_guard_decision": quality_decision,
        "execution_decision": str(row.get("decision", "")),
        "final_reason": final_reason,
        "guard_category": _guard_category(final_reason),
        "score_breakdown": breakdown,
        "score_breakdown_total": total,
        "high_score_explanation": _high_score_explanation(positive, score),
        "htf_bias_direction": context_bias,
        "candidate_side": side,
        "countertrend": _countertrend(side, context_bias),
        "m15_state": _m15_state(row),
        "m5_m1_timing": _m5_m1_timing(row, side),
        "sweep_reclaim_present": _sweep_reclaim_present(row, side),
        "displacement_present": _displacement_present(row, side),
        "quality_guard_detail": _quality_guard_detail(row, side, context_bias, final_reason, config),
        "asia_shadow_classification": asia_class,
        "asia_execution_mode": asia_execution_mode,
        "asia_range_high": _optional_float(row.get("asia_range_high")),
        "asia_range_low": _optional_float(row.get("asia_range_low")),
        "asia_swept_high": _bool(row, "asia_swept_high"),
        "asia_swept_low": _bool(row, "asia_swept_low"),
        "london_manipulation_detected": _bool(row, "london_manipulation_detected"),
        "ny_reversal_candidate": _bool(row, "ny_reversal_candidate"),
    }


def _ensure_diagnostic_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in REJECTION_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    return result


def _context_bias(row: pd.Series) -> str:
    long_bias = _bool(row, "v50_trend4_long") or _bool(row, "v50_soft4_long") or _bool(row, "v50_mom1_long")
    short_bias = _bool(row, "v50_trend4_short") or _bool(row, "v50_soft4_short") or _bool(row, "v50_mom1_short")
    if long_bias and not short_bias:
        return "BULL"
    if short_bias and not long_bias:
        return "BEAR"
    if long_bias and short_bias:
        return "MIXED"
    return "UNKNOWN"


def _quality_guard_decision(row: pd.Series, side: str) -> str:
    if side == "BUY":
        return "PASS" if _bool(row, "v50_quality_long_ok") else "BLOCKED"
    if side == "SELL":
        return "PASS" if _bool(row, "v50_quality_short_ok") else "BLOCKED"
    return "N/A"


def _score_breakdown(row: pd.Series, side: str) -> tuple[str, float, list[str]]:
    if side not in {"BUY", "SELL"}:
        return "", 0.0, []
    suffix = "long" if side == "BUY" else "short"
    sign = 1 if side == "BUY" else -1
    components = {
        "htf": 22.0 if _bool(row, f"v50_trend4_{suffix}") else 11.0 if _bool(row, f"v50_soft4_{suffix}") else 0.0,
        "h1": 20.0 if _bool(row, f"v50_strong1_{suffix}") else 14.0 if _bool(row, f"v50_mom1_{suffix}") else 0.0,
        "m15": 18.0 if _bool(row, f"v50_struct15_{suffix}") else 9.0 if _m15_close_vs_ema50(row, sign) else 0.0,
        "m10": 12.0 if _bool(row, f"v50_trigger10_{suffix}") else 0.0,
        "m5": 10.0 if _bool(row, f"v50_trigger5_{suffix}") else 0.0,
        "liquidity": 7.0 if _bool(row, f"v50_sweep_{suffix}") else 4.0 if _bool(row, f"v50_bos_{suffix}") else 0.0,
        "value": 6.0 if _bool(row, "v50_above_value" if side == "BUY" else "v50_below_value") else 0.0,
        "ema_stack": 4.0 if _ema_stack(row, sign) else 0.0,
        "session": 5.0 if _bool(row, "v50_in_session") else 0.0,
        "volume": 3.0 if _bool(row, "v50_volume_ok") else 0.0,
        "penalty_chase": -10.0 if _bool(row, f"v50_{suffix}_chase_block") else 0.0,
        "penalty_late_impulse": -16.0 if _bool(row, f"v50_late_{suffix}_impulse") else 0.0,
        "penalty_chop": -8.0 if _bool(row, "v50_chop_block") else 0.0,
        "penalty_time_guard": -4.0 if _bool(row, "v50_time_guard") else 0.0,
    }
    total = max(0.0, min(100.0, sum(components.values())))
    positive = [f"{name}+{value:g}" for name, value in components.items() if value > 0]
    breakdown = "; ".join(f"{name}={value:g}" for name, value in components.items())
    return breakdown, total, positive


def _high_score_explanation(positive: list[str], score: float) -> str:
    if score < 60:
        return ""
    return "high setup score from " + (", ".join(positive) if positive else "available V50 score inputs")


def _guard_category(reason: str) -> str:
    lower = str(reason).lower()
    if "asia_context" in lower or "asia_london_context" in lower:
        return "session_context"
    if "session blocked" in lower:
        return "session"
    if "quality guard" in lower or "setup not confirmed" in lower or "adx" in lower:
        return "setup_quality"
    if "score" in lower:
        return "score"
    if "spread" in lower:
        return "spread"
    if "stale" in lower:
        return "stale_data"
    if "future" in lower or "time" in lower:
        return "time_alignment"
    if "max trades" in lower:
        return "max_trades"
    if "risk" in lower or "rr" in lower:
        return "risk_reward"
    if "mtf" in lower or "bias" in lower:
        return "mtf_bias"
    return "other"


def _countertrend(side: str, context_bias: str) -> bool:
    return (side == "BUY" and context_bias == "BEAR") or (side == "SELL" and context_bias == "BULL")


def _m15_state(row: pd.Series) -> str:
    if _bool(row, "v50_struct15_long"):
        return "BULL"
    if _bool(row, "v50_struct15_short"):
        return "BEAR"
    if _value(row, "v50_15m_close") > _value(row, "v50_15m_ema50"):
        return "BULL_SOFT"
    if _value(row, "v50_15m_close") < _value(row, "v50_15m_ema50"):
        return "BEAR_SOFT"
    return "RANGE"


def _m5_m1_timing(row: pd.Series, side: str) -> str:
    suffix = "long" if side == "BUY" else "short"
    m5_ready = _bool(row, f"v50_trigger5_{suffix}")
    m10_ready = _bool(row, f"v50_trigger10_{suffix}")
    return f"M5={'READY' if m5_ready else 'NOT_READY'}; M1=UNAVAILABLE; M10={'READY' if m10_ready else 'NOT_READY'}"


def _sweep_reclaim_present(row: pd.Series, side: str) -> bool:
    suffix = "long" if side == "BUY" else "short"
    return _bool(row, f"v50_sweep_{suffix}")


def _displacement_present(row: pd.Series, side: str) -> bool:
    suffix = "long" if side == "BUY" else "short"
    return _bool(row, f"v50_bos_{suffix}") or (
        _value(row, "v50_candle_body") >= _value(row, "v50_atr") * 0.35
        and _value(row, "v50_adx") >= 16.0
    )


def _quality_guard_detail(
    row: pd.Series,
    side: str,
    context_bias: str,
    final_reason: str,
    config: V51DemoIntradayConfig,
) -> str:
    details = [
        f"HTF bias direction={context_bias}",
        f"candidate side={side}",
        f"countertrend={_countertrend(side, context_bias)}",
        f"M15 state={_m15_state(row)}",
        f"M5/M1 timing={_m5_m1_timing(row, side)}",
        f"sweep/reclaim present={_sweep_reclaim_present(row, side)}",
        f"displacement present={_displacement_present(row, side)}",
        f"asia_range_high={_optional_float(row.get('asia_range_high'))}",
        f"asia_range_low={_optional_float(row.get('asia_range_low'))}",
        f"asia_swept_high={_bool(row, 'asia_swept_high')}",
        f"asia_swept_low={_bool(row, 'asia_swept_low')}",
        f"london_manipulation_detected={_bool(row, 'london_manipulation_detected')}",
        f"ny_reversal_candidate={_bool(row, 'ny_reversal_candidate')}",
        f"asia_london_context_valid={_asia_london_context_valid(row, config)}",
        f"allowed_sessions={','.join(config.allowed_sessions)}",
        f"reason={final_reason}",
    ]
    return " | ".join(details)


def _asia_shadow_classification(row: pd.Series) -> str:
    session = str(row.get("session", "")).upper()
    if session not in {"ASIA", "ASIA/LONDON"}:
        return ""
    if _bool(row, "asia_swept_high") and _bool(row, "asia_swept_low"):
        return "ASIA_FALSE_BREAK"
    if _bool(row, "asia_swept_high"):
        return "ASIA_LIQUIDITY_ABOVE"
    if _bool(row, "asia_swept_low"):
        return "ASIA_LIQUIDITY_BELOW"
    if _bool(row, "v50_sweep_long") and _bool(row, "v50_sweep_short"):
        return "ASIA_FALSE_BREAK"
    if _bool(row, "v50_sweep_short"):
        return "ASIA_LIQUIDITY_ABOVE"
    if _bool(row, "v50_sweep_long"):
        return "ASIA_LIQUIDITY_BELOW"
    if _bool(row, "v50_chop_block") or _value(row, "v50_adx") < 16.0:
        return "ASIA_RANGE_BUILD"
    return "ASIA_ACCUMULATION"


def _asia_execution_mode(row: pd.Series, config: V51DemoIntradayConfig) -> str:
    session = str(row.get("session", "")).upper()
    if session == "ASIA":
        return "SHADOW_ONLY"
    if session == "ASIA/LONDON":
        return "CONTEXT_PASS_REPORT_ONLY" if _asia_london_context_valid(row, config) else "REPORT_ONLY"
    return ""


def _diagnostic_final_reason(row: pd.Series, config: V51DemoIntradayConfig) -> str:
    reason = str(row.get("reason", ""))
    session = str(row.get("session", "")).upper()
    if session == "FX CLOSED":
        return reason
    if session == "ASIA" and reason.lower().startswith("session blocked"):
        return "asia_context_only"
    if session == "ASIA/LONDON" and reason.lower().startswith("session blocked"):
        if _asia_london_context_valid(row, config):
            return "asia_london_context_session_passed_report_only"
        if _bool(row, "asia_swept_high") or _bool(row, "asia_swept_low"):
            return f"{reason} | asia_sweep_context_uncertain_or_quality_blocked"
    return reason


def _asia_london_context_valid(row: pd.Series, config: V51DemoIntradayConfig) -> bool:
    side = str(row.get("side", "")).upper()
    if str(row.get("session", "")).upper() != "ASIA/LONDON":
        return False
    if side not in {"BUY", "SELL"}:
        return False
    if _numeric(row.get("score")) < config.min_score:
        return False
    if _numeric(row.get("score_gap")) < config.min_score_gap:
        return False
    if _quality_guard_decision(row, side) != "PASS":
        return False
    return _asia_sweep_reclaim_matches_side(row, side)


def _asia_sweep_reclaim_matches_side(row: pd.Series, side: str) -> bool:
    asia_high = _numeric(row.get("asia_range_high"))
    asia_low = _numeric(row.get("asia_range_low"))
    close = _numeric(row.get("Close"))
    if asia_high <= 0 or asia_low <= 0 or close <= 0:
        return False
    if side == "SELL":
        return _bool(row, "asia_swept_high") and close <= asia_high
    if side == "BUY":
        return _bool(row, "asia_swept_low") and close >= asia_low
    return False


def _m15_close_vs_ema50(row: pd.Series, sign: int) -> bool:
    close = _value(row, "v50_15m_close")
    ema = _value(row, "v50_15m_ema50")
    return close > ema if sign > 0 else close < ema


def _ema_stack(row: pd.Series, sign: int) -> bool:
    close = _value(row, "Close")
    ema21 = _value(row, "v50_ema21")
    ema50 = _value(row, "v50_ema50")
    return close > ema21 and close > ema50 if sign > 0 else close < ema21 and close < ema50


def _high_score_rejection_lines(candidates: pd.DataFrame) -> list[str]:
    if candidates.empty:
        return []
    rejected = candidates[
        (candidates["decision"].astype(str) != "ACCEPTED")
        & (pd.to_numeric(candidates["score"], errors="coerce").fillna(0.0) >= 60.0)
    ]
    lines = []
    for _, row in rejected.iterrows():
        lines.append(
            f"{row.get('candle_time')} | {row.get('session')} | {row.get('side')} | "
            f"setup_score={row.get('setup_score')} | context_bias={row.get('context_bias')} | "
            f"quality_guard_decision={row.get('quality_guard_decision')} | "
            f"execution_decision={row.get('execution_decision')} | guard={row.get('guard_category')} | "
            f"breakdown={row.get('score_breakdown')} | final_reason={row.get('final_reason')}"
        )
    return lines


def _bool(row: pd.Series, column: str) -> bool:
    value = row.get(column, False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if pd.isna(value):
        return False
    return bool(value)


def _bool_series_sum(series: pd.Series | None) -> int:
    if series is None:
        return 0
    return int(sum(_bool(pd.Series({"value": value}), "value") for value in series))


def _numeric(value: Any) -> float:
    try:
        if value is None or pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _value(row: pd.Series, column: str) -> float:
    return _numeric(row.get(column))


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _last_non_empty(series: pd.Series | None) -> str:
    if series is None:
        return "n/a"
    values = series.dropna()
    if values.empty:
        return "n/a"
    return str(values.iloc[-1])


def _naive_timestamp(value: Any) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except Exception:
        return pd.NaT
    if pd.isna(timestamp):
        return pd.NaT
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp


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
    paths["session_behavior_latest"].write_text(
        "\n".join(
            [
                "V51 Session Behavior",
                "=" * 72,
                f"Status: {status}",
                f"Reason: {reason}",
                "No orders were sent. This is diagnostics only.",
                "",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
