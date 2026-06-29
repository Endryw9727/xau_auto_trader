"""Join V51 candidates with Asia/London/New York market structure (read-only).

This diagnostic answers the FASE 1 market-structure questions: did Asia build a
range, did London sweep its liquidity, was it reclaimed, did New York reverse,
and where do V51 candidates (accepted and rejected) sit relative to that
structure and the key Asia/London levels.

It never imports execution code, never sends orders and never changes config.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.v51_structure_context import (
    STRUCTURE_CONTEXT_COLUMNS,
    STRUCTURE_SUMMARY_COLUMNS,
    annotate_candidates_with_structure,
    build_structure_context_summary,
)
from src.data_feed.market_data import load_csv_data
from src.strategy_lab.strategy_v51_demo_intraday import (
    DEFAULT_V51_CONFIG_PATH,
    build_demo_intraday_decision_log,
    load_v51_config,
)


DEFAULT_OUTPUT_DIR = Path("reports/diagnostics")
DEFAULT_CONTEXT_CSV = "v51_market_structure_context.csv"
DEFAULT_SUMMARY_CSV = "v51_market_structure_summary.csv"
DEFAULT_LATEST_TXT = "v51_market_structure_latest.txt"
DEFAULT_XAUUSD_CSV_PATH = Path("data/raw/xauusd.csv")


@dataclass(frozen=True)
class V51MarketStructureResult:
    """Status and paths for one generated market-structure report."""

    status: str
    reason: str
    context_path: Path
    summary_path: Path
    latest_path: Path


def run_v51_market_structure_diagnostics(
    *,
    candles: int = 200,
    config_path: str | Path = DEFAULT_V51_CONFIG_PATH,
    csv_path: str | Path = DEFAULT_XAUUSD_CSV_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> V51MarketStructureResult:
    """Generate the V51 market-structure context report."""
    if candles <= 0:
        raise ValueError("candles must be positive")

    paths = structure_paths(output_dir)
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
    annotated = annotate_candidates_with_structure(decision_log, working_data)
    if annotated.empty:
        return _write_empty(paths, "NO_CANDIDATES", "No BUY/SELL candidates to annotate")

    summary = build_structure_context_summary(annotated)
    annotated.to_csv(paths["context"], index=False)
    summary.to_csv(paths["summary"], index=False)
    paths["latest"].write_text(_build_latest_text(annotated, summary), encoding="utf-8")
    return V51MarketStructureResult(
        "OK", "V51 market structure report generated", paths["context"], paths["summary"], paths["latest"]
    )


def _build_latest_text(annotated: pd.DataFrame, summary: pd.DataFrame) -> str:
    total = int(len(annotated))
    aligned = int((annotated["structure_alignment"] == "aligned").sum())
    counter = int((annotated["structure_alignment"] == "counter").sum())
    accepted = int((annotated["decision"].astype(str).str.upper() == "ACCEPTED").sum())
    sweep_days = annotated[annotated["manipulation_label"].astype(str).str.contains("reclaimed", na=False)]

    lines = [
        "V51 Market Structure Context",
        "=" * 72,
        f"Total candidates: {total}",
        f"Accepted candidates: {accepted}",
        f"Aligned with sweep-reclaim: {aligned}",
        f"Counter to sweep-reclaim: {counter}",
        f"Candidates on reclaimed-sweep days: {int(len(sweep_days))}",
        "",
        "By manipulation_label x alignment",
        "-" * 72,
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"{row['manipulation_label']} | {row['structure_alignment']} | "
            f"candidates={row['candidates']} | accepted={row['accepted']} | "
            f"rejected={row['rejected']} | BUY={row['buy']} SELL={row['sell']}"
        )
    lines.append("")
    lines.append("No orders were sent. This is diagnostics only.")
    return "\n".join(lines) + "\n"


def structure_paths(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    """Return output paths for the market-structure report."""
    directory = Path(output_dir)
    return {
        "context": directory / DEFAULT_CONTEXT_CSV,
        "summary": directory / DEFAULT_SUMMARY_CSV,
        "latest": directory / DEFAULT_LATEST_TXT,
    }


def _write_empty(paths: dict[str, Path], status: str, reason: str) -> V51MarketStructureResult:
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=STRUCTURE_CONTEXT_COLUMNS).to_csv(paths["context"], index=False)
    pd.DataFrame(columns=STRUCTURE_SUMMARY_COLUMNS).to_csv(paths["summary"], index=False)
    paths["latest"].write_text(
        "\n".join(
            [
                "V51 Market Structure Context",
                "=" * 72,
                f"Status: {status}",
                f"Reason: {reason}",
                "No orders were sent. This is diagnostics only.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return V51MarketStructureResult(status, reason, paths["context"], paths["summary"], paths["latest"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candles", type=int, default=200, help="Latest closed candles to analyze.")
    parser.add_argument("--config", type=Path, default=DEFAULT_V51_CONFIG_PATH, help="V51 config path.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_XAUUSD_CSV_PATH, help="Local OHLCV CSV path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Report output directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_v51_market_structure_diagnostics(
        candles=args.candles,
        config_path=args.config,
        csv_path=args.csv,
        output_dir=args.output_dir,
    )
    print("=" * 72)
    print("XAU Auto Trader - V51 Market Structure Context")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print(f"Context: {result.context_path}")
    print(f"Summary: {result.summary_path}")
    print(f"Latest: {result.latest_path}")
    print("No orders were sent. This is diagnostics only.")


if __name__ == "__main__":
    main()
