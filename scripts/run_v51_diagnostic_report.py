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


DEFAULT_V51_DIAGNOSTIC_OUTPUT_DIR = Path("reports/diagnostics")
DEFAULT_V51_DIAGNOSTIC_SUMMARY = "v51_diagnostic_summary.csv"
DEFAULT_V51_DIAGNOSTIC_REJECTIONS = "v51_diagnostic_rejections.csv"
DEFAULT_V51_DIAGNOSTIC_LATEST = "v51_diagnostic_latest.txt"
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


@dataclass(frozen=True)
class V51DiagnosticReportResult:
    """Paths and status for one generated V51 diagnostic report."""

    status: str
    reason: str
    summary_path: Path
    rejections_path: Path
    latest_path: Path


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
        return V51DiagnosticReportResult("ERROR", reason, paths["summary"], paths["rejections"], paths["latest"])

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
        return V51DiagnosticReportResult("INSUFFICIENT_DATA", reason, paths["summary"], paths["rejections"], paths["latest"])

    working_data = data.tail(config.warmup_candles + candles).copy()
    decision_log = build_demo_intraday_decision_log(working_data, config, enforce_daily_limit=False)
    decision_log = _latest_decisions(decision_log, candles)
    summary = build_diagnostic_summary(
        decision_log,
        config,
        config_path=config_path,
        csv_path=csv_path,
        requested_candles=candles,
        candles_loaded=len(data),
    )
    rejections = build_rejections_report(decision_log)
    latest_text = build_latest_text(summary.iloc[0].to_dict(), decision_log)

    summary.to_csv(paths["summary"], index=False)
    rejections.to_csv(paths["rejections"], index=False)
    paths["latest"].write_text(latest_text, encoding="utf-8")
    return V51DiagnosticReportResult("OK", "V51 diagnostic report generated", paths["summary"], paths["rejections"], paths["latest"])


def build_diagnostic_summary(
    decision_log: pd.DataFrame,
    config: V51DemoIntradayConfig,
    *,
    config_path: Path,
    csv_path: Path,
    requested_candles: int,
    candles_loaded: int,
) -> pd.DataFrame:
    """Return a one-row summary for the V51 diagnostic report."""
    candidates = _candidate_rows(decision_log)
    accepted = candidates[candidates["decision"] == "ACCEPTED"] if not candidates.empty else candidates
    rejected = candidates[candidates["decision"] != "ACCEPTED"] if not candidates.empty else candidates
    sessions = decision_log["session"].astype(str) if "session" in decision_log.columns and not decision_log.empty else pd.Series(dtype=str)
    latest = _latest_timestamp(decision_log)
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


def build_latest_text(summary_row: dict[str, Any], decision_log: pd.DataFrame) -> str:
    """Build a compact human-readable latest-candidate diagnostic."""
    candidates = _candidate_rows(decision_log).tail(10)
    lines = [
        "V51 Diagnostic Report",
        "=" * 72,
        f"Status: {summary_row.get('status')}",
        f"Reason: {summary_row.get('reason')}",
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


def diagnostic_paths(output_dir: str | Path = DEFAULT_V51_DIAGNOSTIC_OUTPUT_DIR) -> dict[str, Path]:
    """Return output paths for the V51 diagnostic report."""
    directory = Path(output_dir)
    return {
        "summary": directory / DEFAULT_V51_DIAGNOSTIC_SUMMARY,
        "rejections": directory / DEFAULT_V51_DIAGNOSTIC_REJECTIONS,
        "latest": directory / DEFAULT_V51_DIAGNOSTIC_LATEST,
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


def _latest_timestamp(decision_log: pd.DataFrame) -> pd.Timestamp | None:
    if decision_log.empty or "candle_time" not in decision_log.columns:
        return None
    times = pd.to_datetime(decision_log["candle_time"], errors="coerce").dropna()
    if times.empty:
        return None
    return pd.Timestamp(times.max())


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


if __name__ == "__main__":
    main()
