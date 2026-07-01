"""V51 quality-review diagnostics: RR quality, false negatives, rejection review.

This Phase-2 report simulates the theoretical outcome of every directional V51
candidate (accepted and rejected) and then asks: do higher RR candidates perform
better, how many candidates blocked by discretionary quality filters would have
won, and which rejection categories would have been profitable and deserve a
human review.

It is research only. It never imports execution code, never sends orders and
never changes config. A positive theoretical result is a prompt to review a
filter, never an instruction to weaken it.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.v51_outcome_simulation import simulate_candidate_outcomes
from src.analysis.v51_quality_review import (
    FALSE_NEGATIVE_COLUMNS,
    REJECTION_REVIEW_COLUMNS,
    RR_QUALITY_COLUMNS,
    build_quality_guard_false_negatives,
    build_rejection_review,
    build_rr_quality,
)
from src.data_feed.market_data import load_csv_data
from src.strategy_lab.strategy_v51_demo_intraday import (
    DEFAULT_V51_CONFIG_PATH,
    build_demo_intraday_decision_log,
    load_v51_config,
)


DEFAULT_OUTPUT_DIR = Path("reports/diagnostics")
DEFAULT_RR_CSV = "v51_quality_rr.csv"
DEFAULT_REVIEW_CSV = "v51_quality_rejection_review.csv"
DEFAULT_FALSE_NEG_CSV = "v51_quality_false_negatives.csv"
DEFAULT_LATEST_TXT = "v51_quality_review_latest.txt"
DEFAULT_XAUUSD_CSV_PATH = Path("data/raw/xauusd.csv")


@dataclass(frozen=True)
class V51QualityReviewResult:
    """Status and paths for one generated quality-review report."""

    status: str
    reason: str
    rr_path: Path
    review_path: Path
    false_negatives_path: Path
    latest_path: Path


def run_v51_quality_review(
    *,
    candles: int = 400,
    max_horizon_candles: int = 32,
    config_path: str | Path = DEFAULT_V51_CONFIG_PATH,
    csv_path: str | Path = DEFAULT_XAUUSD_CSV_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> V51QualityReviewResult:
    """Generate the V51 quality-review report."""
    if candles <= 0:
        raise ValueError("candles must be positive")

    paths = quality_review_paths(output_dir)
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
    outcomes = simulate_candidate_outcomes(decision_log, working_data, max_horizon_candles=max_horizon_candles)
    if outcomes.empty:
        return _write_empty(paths, "NO_CANDIDATES", "No BUY/SELL candidates to simulate")

    outcomes = _attach_reason(outcomes, decision_log)
    rr_quality = build_rr_quality(outcomes)
    rejection_review = build_rejection_review(outcomes)
    false_negatives = build_quality_guard_false_negatives(outcomes)

    rr_quality.to_csv(paths["rr"], index=False)
    rejection_review.to_csv(paths["review"], index=False)
    false_negatives.to_csv(paths["false_negatives"], index=False)
    paths["latest"].write_text(
        _build_latest_text(rr_quality, rejection_review, false_negatives), encoding="utf-8"
    )
    return V51QualityReviewResult(
        "OK",
        "V51 quality review generated",
        paths["rr"],
        paths["review"],
        paths["false_negatives"],
        paths["latest"],
    )


def _attach_reason(outcomes: pd.DataFrame, decision_log: pd.DataFrame) -> pd.DataFrame:
    if "reason" in outcomes.columns or "signal_id" not in decision_log.columns:
        return outcomes
    reasons = decision_log[["signal_id", "reason"]].drop_duplicates("signal_id")
    return outcomes.merge(reasons, on="signal_id", how="left")


def _build_latest_text(
    rr_quality: pd.DataFrame,
    rejection_review: pd.DataFrame,
    false_negatives: pd.DataFrame,
) -> str:
    flagged = rejection_review[rejection_review["review_flag"]] if not rejection_review.empty else rejection_review
    lines = [
        "V51 Quality Review",
        "=" * 72,
        "",
        "RR quality (by risk/reward bucket)",
        "-" * 72,
    ]
    lines.extend(_table_lines(rr_quality, ["rr_bucket", "trades", "win_rate", "avg_r", "expectancy"]))

    lines += ["", "Rejection review (theoretical performance if not blocked)", "-" * 72]
    lines.extend(
        _table_lines(rejection_review, ["rejection_category", "disposition", "trades", "avg_r", "expectancy", "review_flag"])
    )
    lines += [
        "",
        f"Review candidates (positive expectancy, non-safety filter): {int(len(flagged))}",
    ]

    lines += ["", "Quality-guard false negatives", "-" * 72]
    lines.extend(
        _table_lines(
            false_negatives,
            ["rejection_category", "blocked_candidates", "theoretical_wins", "foregone_total_r", "avg_r"],
        )
    )
    lines += [
        "",
        "Note: theoretical metrics on the full historical decision log. A positive",
        "result is a prompt to review a filter, never to weaken it.",
        "No orders were sent. This is diagnostics only.",
        "",
    ]
    return "\n".join(lines) + "\n"


def _table_lines(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    if frame is None or frame.empty:
        return ["(no rows)"]
    available = [column for column in columns if column in frame.columns]
    lines = [" | ".join(available)]
    for _, row in frame.iterrows():
        lines.append(" | ".join(str(row[column]) for column in available))
    return lines


def quality_review_paths(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    """Return output paths for the quality-review report."""
    directory = Path(output_dir)
    return {
        "rr": directory / DEFAULT_RR_CSV,
        "review": directory / DEFAULT_REVIEW_CSV,
        "false_negatives": directory / DEFAULT_FALSE_NEG_CSV,
        "latest": directory / DEFAULT_LATEST_TXT,
    }


def _write_empty(paths: dict[str, Path], status: str, reason: str) -> V51QualityReviewResult:
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=RR_QUALITY_COLUMNS).to_csv(paths["rr"], index=False)
    pd.DataFrame(columns=REJECTION_REVIEW_COLUMNS).to_csv(paths["review"], index=False)
    pd.DataFrame(columns=FALSE_NEGATIVE_COLUMNS).to_csv(paths["false_negatives"], index=False)
    paths["latest"].write_text(
        "\n".join(
            [
                "V51 Quality Review",
                "=" * 72,
                f"Status: {status}",
                f"Reason: {reason}",
                "No orders were sent. This is diagnostics only.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return V51QualityReviewResult(
        status, reason, paths["rr"], paths["review"], paths["false_negatives"], paths["latest"]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candles", type=int, default=400, help="Latest closed candles to evaluate.")
    parser.add_argument("--horizon", type=int, default=32, help="Max candles to hold each simulated trade.")
    parser.add_argument("--config", type=Path, default=DEFAULT_V51_CONFIG_PATH, help="V51 config path.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_XAUUSD_CSV_PATH, help="Local OHLCV CSV path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Report output directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_v51_quality_review(
        candles=args.candles,
        max_horizon_candles=args.horizon,
        config_path=args.config,
        csv_path=args.csv,
        output_dir=args.output_dir,
    )
    print("=" * 72)
    print("XAU Auto Trader - V51 Quality Review")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print(f"RR quality: {result.rr_path}")
    print(f"Rejection review: {result.review_path}")
    print(f"False negatives: {result.false_negatives_path}")
    print(f"Latest: {result.latest_path}")
    print("No orders were sent. This is diagnostics only.")


if __name__ == "__main__":
    main()
