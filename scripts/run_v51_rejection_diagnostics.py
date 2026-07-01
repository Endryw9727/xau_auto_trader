"""Build a categorized V51 rejection-taxonomy report from local data.

This script is diagnostics only. It reuses the existing V51 decision log (or an
existing reasons CSV) and groups rejections into stable categories so it is easy
to see which filter blocks the most candidates and whether that filter is
safety-critical or a tunable threshold worth reviewing.

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

from src.analysis.v51_rejection_taxonomy import (
    TAXONOMY_SUMMARY_COLUMNS,
    build_rejection_taxonomy,
    classify_decision_log,
    top_blocking_category,
)
from src.data_feed.market_data import load_csv_data
from src.strategy_lab.strategy_v51_demo_intraday import (
    DEFAULT_V51_CONFIG_PATH,
    build_demo_intraday_decision_log,
    load_v51_config,
)


DEFAULT_OUTPUT_DIR = Path("reports/diagnostics")
DEFAULT_TAXONOMY_SUMMARY = "v51_rejection_taxonomy.csv"
DEFAULT_TAXONOMY_LATEST = "v51_rejection_taxonomy_latest.txt"
DEFAULT_XAUUSD_CSV_PATH = Path("data/raw/xauusd.csv")


@dataclass(frozen=True)
class V51RejectionDiagnosticsResult:
    """Status and paths for one generated rejection-taxonomy report."""

    status: str
    reason: str
    summary_path: Path
    latest_path: Path


def run_v51_rejection_diagnostics(
    *,
    candles: int = 200,
    config_path: str | Path = DEFAULT_V51_CONFIG_PATH,
    csv_path: str | Path = DEFAULT_XAUUSD_CSV_PATH,
    reasons_csv: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> V51RejectionDiagnosticsResult:
    """Generate a categorized V51 rejection-taxonomy report."""
    if candles <= 0:
        raise ValueError("candles must be positive")

    paths = taxonomy_paths(output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    try:
        decision_log = _load_decision_log(
            candles=candles,
            config_path=config_path,
            csv_path=csv_path,
            reasons_csv=reasons_csv,
        )
    except FileNotFoundError as exc:
        return _write_empty(paths, "ERROR", str(exc))
    except Exception as exc:  # noqa: BLE001 - report any load error, never raise
        return _write_empty(paths, "ERROR", str(exc))

    taxonomy = build_rejection_taxonomy(decision_log)
    if taxonomy.empty:
        return _write_empty(paths, "NO_CANDIDATES", "No BUY/SELL candidates to classify")

    taxonomy.to_csv(paths["summary"], index=False)
    paths["latest"].write_text(_build_latest_text(taxonomy, decision_log), encoding="utf-8")
    return V51RejectionDiagnosticsResult("OK", "V51 rejection taxonomy generated", paths["summary"], paths["latest"])


def _load_decision_log(
    *,
    candles: int,
    config_path: str | Path,
    csv_path: str | Path,
    reasons_csv: str | Path | None,
) -> pd.DataFrame:
    if reasons_csv is not None:
        path = Path(reasons_csv)
        if not path.exists():
            raise FileNotFoundError(f"reasons CSV not found: {path}")
        return pd.read_csv(path)

    config = load_v51_config(config_path)
    data = load_csv_data(csv_path)
    required_rows = config.warmup_candles + 1
    if len(data) < required_rows:
        raise ValueError(f"dataset insufficient: rows={len(data)}, required_min_rows={required_rows}")
    working_data = data.tail(config.warmup_candles + candles).copy()
    return build_demo_intraday_decision_log(working_data, config, enforce_daily_limit=False)


def _build_latest_text(taxonomy: pd.DataFrame, decision_log: pd.DataFrame) -> str:
    classified = classify_decision_log(decision_log)
    total = int(len(classified))
    accepted = int((classified["rejection_category"] == "accepted").sum()) if not classified.empty else 0
    blocking = top_blocking_category(taxonomy)
    by_disposition = taxonomy.groupby("disposition")["count"].sum().to_dict() if not taxonomy.empty else {}

    lines = [
        "V51 Rejection Taxonomy",
        "=" * 72,
        f"Total candidates: {total}",
        f"Accepted candidates: {accepted}",
        f"Top blocking category: {blocking or 'none'}",
        "By disposition: "
        + ("; ".join(f"{key}={int(value)}" for key, value in sorted(by_disposition.items())) or "none"),
        "",
        "Categories",
        "-" * 72,
    ]
    for _, row in taxonomy.iterrows():
        lines.append(
            f"{row['rejection_category']} | {row['disposition']} | count={row['count']} | "
            f"share={row['share_pct']}% | BUY={row['buy_count']} SELL={row['sell_count']} | "
            f"sessions={row['top_sessions']} | e.g. {row['example_reason']}"
        )
    lines.append("")
    lines.append("No orders were sent. This is diagnostics only.")
    return "\n".join(lines) + "\n"


def taxonomy_paths(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    """Return output paths for the rejection-taxonomy report."""
    directory = Path(output_dir)
    return {
        "summary": directory / DEFAULT_TAXONOMY_SUMMARY,
        "latest": directory / DEFAULT_TAXONOMY_LATEST,
    }


def _write_empty(paths: dict[str, Path], status: str, reason: str) -> V51RejectionDiagnosticsResult:
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=TAXONOMY_SUMMARY_COLUMNS).to_csv(paths["summary"], index=False)
    paths["latest"].write_text(
        "\n".join(
            [
                "V51 Rejection Taxonomy",
                "=" * 72,
                f"Status: {status}",
                f"Reason: {reason}",
                "No orders were sent. This is diagnostics only.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return V51RejectionDiagnosticsResult(status, reason, paths["summary"], paths["latest"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candles", type=int, default=200, help="Latest closed candles to classify.")
    parser.add_argument("--config", type=Path, default=DEFAULT_V51_CONFIG_PATH, help="V51 config path.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_XAUUSD_CSV_PATH, help="Local OHLCV CSV path.")
    parser.add_argument(
        "--reasons-csv",
        type=Path,
        default=None,
        help="Optional existing CSV with a 'reason' column (e.g. a demo execution log) to classify instead.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Report output directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_v51_rejection_diagnostics(
        candles=args.candles,
        config_path=args.config,
        csv_path=args.csv,
        reasons_csv=args.reasons_csv,
        output_dir=args.output_dir,
    )
    print("=" * 72)
    print("XAU Auto Trader - V51 Rejection Taxonomy")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print(f"Summary: {result.summary_path}")
    print(f"Latest: {result.latest_path}")
    print("No orders were sent. This is diagnostics only.")


if __name__ == "__main__":
    main()
