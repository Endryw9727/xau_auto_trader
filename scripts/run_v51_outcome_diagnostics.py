"""Theoretical V51 outcome diagnostics per session, direction and score (read-only).

This simulates the theoretical outcome of V51 candidates by walking forward over
later closed candles (no lookahead, stop-first on ambiguous candles) and reports
performance per session, per direction and across minimum-score thresholds. It is
research/backtest only: it never imports execution code, never sends orders and
never changes config.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.v51_outcome_simulation import (
    OUTCOME_COLUMNS,
    PERFORMANCE_COLUMNS,
    build_performance_summary,
    build_score_threshold_curve,
    simulate_candidate_outcomes,
)
from src.data_feed.market_data import load_csv_data
from src.strategy_lab.strategy_v51_demo_intraday import (
    DEFAULT_V51_CONFIG_PATH,
    build_demo_intraday_decision_log,
    load_v51_config,
)


DEFAULT_OUTPUT_DIR = Path("reports/diagnostics")
DEFAULT_OUTCOMES_CSV = "v51_outcomes.csv"
DEFAULT_BY_SESSION_CSV = "v51_performance_by_session.csv"
DEFAULT_BY_SIDE_CSV = "v51_performance_by_side.csv"
DEFAULT_SCORE_CURVE_CSV = "v51_performance_score_curve.csv"
DEFAULT_LATEST_TXT = "v51_outcome_latest.txt"
DEFAULT_XAUUSD_CSV_PATH = Path("data/raw/xauusd.csv")


@dataclass(frozen=True)
class V51OutcomeDiagnosticsResult:
    """Status and paths for one generated outcome-diagnostics report."""

    status: str
    reason: str
    outcomes_path: Path
    by_session_path: Path
    by_side_path: Path
    score_curve_path: Path
    latest_path: Path


def run_v51_outcome_diagnostics(
    *,
    candles: int = 400,
    max_horizon_candles: int = 32,
    accepted_only: bool = False,
    config_path: str | Path = DEFAULT_V51_CONFIG_PATH,
    csv_path: str | Path = DEFAULT_XAUUSD_CSV_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> V51OutcomeDiagnosticsResult:
    """Generate the V51 theoretical outcome diagnostics reports."""
    if candles <= 0:
        raise ValueError("candles must be positive")

    paths = outcome_paths(output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    try:
        config = load_v51_config(config_path)
        data = load_csv_data(csv_path)
    except Exception as exc:  # noqa: BLE001 - report any load error, never raise
        return _write_empty(paths, "ERROR", str(exc))

    required_rows = config.warmup_candles + 1
    if len(data) < required_rows:
        return _write_empty(
            paths, "INSUFFICIENT_DATA", f"dataset insufficient: rows={len(data)}, required_min_rows={required_rows}"
        )

    working_data = data.tail(config.warmup_candles + candles).copy()
    decision_log = build_demo_intraday_decision_log(working_data, config, enforce_daily_limit=False)
    outcomes = simulate_candidate_outcomes(
        decision_log, working_data, max_horizon_candles=max_horizon_candles, accepted_only=accepted_only
    )
    if outcomes.empty:
        return _write_empty(paths, "NO_CANDIDATES", "No directional candidates to simulate")

    by_session = build_performance_summary(outcomes, by="session")
    by_side = build_performance_summary(outcomes, by="side")
    score_curve = build_score_threshold_curve(outcomes)

    outcomes.to_csv(paths["outcomes"], index=False)
    by_session.to_csv(paths["by_session"], index=False)
    by_side.to_csv(paths["by_side"], index=False)
    score_curve.to_csv(paths["score_curve"], index=False)
    paths["latest"].write_text(_build_latest_text(outcomes, by_session, by_side, score_curve), encoding="utf-8")
    return V51OutcomeDiagnosticsResult(
        "OK",
        "V51 outcome diagnostics generated",
        paths["outcomes"],
        paths["by_session"],
        paths["by_side"],
        paths["score_curve"],
        paths["latest"],
    )


def _build_latest_text(
    outcomes: pd.DataFrame,
    by_session: pd.DataFrame,
    by_side: pd.DataFrame,
    score_curve: pd.DataFrame,
) -> str:
    simulated = outcomes[outcomes["outcome"].isin(["WIN", "LOSS", "TIMEOUT"])]
    total = int(len(simulated))
    wins = int((simulated["outcome"] == "WIN").sum())
    total_r = round(float(pd.to_numeric(simulated["r_multiple"], errors="coerce").sum()), 4)

    lines = [
        "V51 Theoretical Outcome Diagnostics",
        "=" * 72,
        f"Simulated candidates: {total}",
        f"Wins: {wins} | Win rate: {round(100.0 * wins / total, 2) if total else 0.0}%",
        f"Total R: {total_r} | Expectancy: {round(total_r / total, 4) if total else 0.0} R/trade",
        "",
        "Per direction (BUY/SELL)",
        "-" * 72,
    ]
    lines.extend(_format_perf_rows(by_side))
    lines.append("")
    lines.append("Per session")
    lines.append("-" * 72)
    lines.extend(_format_perf_rows(by_session))
    lines.append("")
    lines.append("Minimum-score effectiveness")
    lines.append("-" * 72)
    lines.extend(_format_perf_rows(score_curve))
    lines.append("")
    lines.append("Theoretical simulation only. No orders were sent. This is diagnostics only.")
    return "\n".join(lines) + "\n"


def _format_perf_rows(summary: pd.DataFrame) -> list[str]:
    if summary.empty:
        return ["(no data)"]
    return [
        f"{row['group']} | trades={row['trades']} | win_rate={row['win_rate']}% | "
        f"avg_R={row['avg_r']} | total_R={row['total_r']} | expectancy={row['expectancy']}"
        for _, row in summary.iterrows()
    ]


def outcome_paths(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    """Return output paths for the outcome diagnostics."""
    directory = Path(output_dir)
    return {
        "outcomes": directory / DEFAULT_OUTCOMES_CSV,
        "by_session": directory / DEFAULT_BY_SESSION_CSV,
        "by_side": directory / DEFAULT_BY_SIDE_CSV,
        "score_curve": directory / DEFAULT_SCORE_CURVE_CSV,
        "latest": directory / DEFAULT_LATEST_TXT,
    }


def _write_empty(paths: dict[str, Path], status: str, reason: str) -> V51OutcomeDiagnosticsResult:
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=OUTCOME_COLUMNS).to_csv(paths["outcomes"], index=False)
    for key in ("by_session", "by_side", "score_curve"):
        pd.DataFrame(columns=PERFORMANCE_COLUMNS).to_csv(paths[key], index=False)
    paths["latest"].write_text(
        "\n".join(
            [
                "V51 Theoretical Outcome Diagnostics",
                "=" * 72,
                f"Status: {status}",
                f"Reason: {reason}",
                "Theoretical simulation only. No orders were sent. This is diagnostics only.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return V51OutcomeDiagnosticsResult(
        status, reason, paths["outcomes"], paths["by_session"], paths["by_side"], paths["score_curve"], paths["latest"]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candles", type=int, default=400, help="Latest closed candles to evaluate.")
    parser.add_argument("--max-horizon", type=int, default=32, help="Max candles to hold before TIMEOUT.")
    parser.add_argument("--accepted-only", action="store_true", help="Simulate only ACCEPTED candidates.")
    parser.add_argument("--config", type=Path, default=DEFAULT_V51_CONFIG_PATH, help="V51 config path.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_XAUUSD_CSV_PATH, help="Local OHLCV CSV path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Report output directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_v51_outcome_diagnostics(
        candles=args.candles,
        max_horizon_candles=args.max_horizon,
        accepted_only=args.accepted_only,
        config_path=args.config,
        csv_path=args.csv,
        output_dir=args.output_dir,
    )
    print("=" * 72)
    print("XAU Auto Trader - V51 Theoretical Outcome Diagnostics")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print(f"Outcomes: {result.outcomes_path}")
    print(f"By session: {result.by_session_path}")
    print(f"By side: {result.by_side_path}")
    print(f"Score curve: {result.score_curve_path}")
    print(f"Latest: {result.latest_path}")
    print("Theoretical simulation only. No orders were sent. This is diagnostics only.")


if __name__ == "__main__":
    main()
