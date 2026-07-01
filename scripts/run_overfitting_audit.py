"""Run the overfitting-resistance audit over the whole edge family (read-only).

Reads config/edge_lab.yaml, builds the per-strategy daily return matrix for every
instrument's session/direction strategies, then computes the Deflated Sharpe Ratio
and the Probability of Backtest Overfitting (PBO via CSCV) for the family as a
whole. This answers: "given how much we searched, is the best strategy real, or
what luck produces?"

It never imports execution code, never sends orders and never changes config.
Missing CSVs are skipped, not an error.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.edge_overfitting import overfitting_audit, session_return_series
from src.data_feed.market_data import load_csv_data


DEFAULT_CONFIG_PATH = Path("config/edge_lab.yaml")
DEFAULT_OUTPUT_DIR = Path("reports/diagnostics")
DEFAULT_SUMMARY_CSV = "overfitting_summary.csv"
DEFAULT_STRATEGIES_CSV = "overfitting_strategies.csv"
DEFAULT_LATEST_TXT = "overfitting_latest.txt"

SUMMARY_COLUMNS = (
    "status",
    "n_strategies",
    "n_days",
    "best_strategy",
    "best_sharpe",
    "expected_max_sharpe_under_null",
    "deflated_sharpe_ratio",
    "probability_of_backtest_overfitting",
    "pbo_n_combinations",
    "live_armed",
)


@dataclass(frozen=True)
class OverfittingAuditResult:
    status: str
    reason: str
    summary_path: Path
    strategies_path: Path
    latest_path: Path


def run_overfitting_audit(
    *,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    n_splits: int = 16,
) -> OverfittingAuditResult:
    """Compute DSR + PBO for the whole session-edge family across instruments."""
    paths = _paths(output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    try:
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        return _write_empty(paths, "ERROR", str(exc))

    instruments = config.get("instruments", [])
    if not instruments:
        return _write_empty(paths, "ERROR", "no instruments configured")

    series_by_strategy: dict[str, pd.Series] = {}
    for instrument in instruments:
        symbol = str(instrument.get("symbol", "?"))
        csv_path = Path(instrument.get("csv", ""))
        cost = float(instrument.get("cost_per_trade", 0.0))
        if not csv_path.exists():
            continue
        try:
            data = load_csv_data(csv_path)
            series_by_strategy.update(session_return_series(data, symbol, cost_per_trade=cost))
        except Exception:  # noqa: BLE001 - skip an unreadable instrument, keep the family
            continue

    audit = overfitting_audit(series_by_strategy, n_splits=n_splits)
    _write_reports(paths, audit)
    reason = audit.get("status", "OK")
    return OverfittingAuditResult("OK", reason, paths["summary"], paths["strategies"], paths["latest"])


def _write_reports(paths: dict[str, Path], audit: dict) -> None:
    summary = {col: audit.get(col) for col in SUMMARY_COLUMNS}
    summary["status"] = audit.get("status", "OK")
    summary["live_armed"] = False
    pd.DataFrame([summary], columns=SUMMARY_COLUMNS).to_csv(paths["summary"], index=False)

    strategies = audit.get("strategies", [])
    pd.DataFrame(strategies, columns=("strategy", "sharpe")).to_csv(paths["strategies"], index=False)

    paths["latest"].write_text(_build_latest_text(audit), encoding="utf-8")


def _build_latest_text(audit: dict) -> str:
    dsr = audit.get("deflated_sharpe_ratio")
    pbo = audit.get("probability_of_backtest_overfitting")
    verdict = _verdict(dsr, pbo)
    lines = [
        "Edge Overfitting Audit (Deflated Sharpe + PBO)",
        "=" * 72,
        f"Status: {audit.get('status', 'OK')}",
        f"Strategies searched: {audit.get('n_strategies', 0)}",
        f"Days: {audit.get('n_days', 0)}",
        f"Best strategy: {audit.get('best_strategy', '-')}  (Sharpe {audit.get('best_sharpe', '-')})",
        f"Expected max Sharpe under the null (luck): {audit.get('expected_max_sharpe_under_null', '-')}",
        f"Deflated Sharpe Ratio (DSR): {dsr}",
        f"Probability of Backtest Overfitting (PBO): {pbo}",
        "",
        f"Verdict: {verdict}",
        "",
        "DSR is the probability the best strategy's Sharpe beats what searching",
        "this many strategies would produce by luck; PBO is how often the best",
        "in-sample strategy lands below the out-of-sample median. A real edge needs",
        "DSR high (>~0.95) AND PBO low (<~0.5). This is research only. No orders.",
        "",
    ]
    return "\n".join(lines) + "\n"


def _verdict(dsr, pbo) -> str:
    if dsr is None or pbo is None:
        return "INSUFFICIENT DATA"
    if dsr >= 0.95 and pbo <= 0.5:
        return "SURVIVES (search-adjusted edge; still validate live-safe)"
    return "NOT ROBUST (consistent with overfitting / luck)"


def _paths(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    directory = Path(output_dir)
    return {
        "summary": directory / DEFAULT_SUMMARY_CSV,
        "strategies": directory / DEFAULT_STRATEGIES_CSV,
        "latest": directory / DEFAULT_LATEST_TXT,
    }


def _write_empty(paths: dict[str, Path], status: str, reason: str) -> OverfittingAuditResult:
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=SUMMARY_COLUMNS).to_csv(paths["summary"], index=False)
    pd.DataFrame(columns=("strategy", "sharpe")).to_csv(paths["strategies"], index=False)
    paths["latest"].write_text(
        "\n".join(
            ["Edge Overfitting Audit", "=" * 72, f"Status: {status}", f"Reason: {reason}",
             "No orders were sent. This is diagnostics only.", ""]
        ),
        encoding="utf-8",
    )
    return OverfittingAuditResult(status, reason, paths["summary"], paths["strategies"], paths["latest"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Edge lab config path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Report output directory.")
    parser.add_argument("--n-splits", type=int, default=16, help="CSCV splits (even number).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_overfitting_audit(config_path=args.config, output_dir=args.output_dir, n_splits=args.n_splits)
    print("=" * 72)
    print("XAU Auto Trader - Edge Overfitting Audit (DSR + PBO)")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Summary: {result.summary_path}")
    print(f"Strategies: {result.strategies_path}")
    print(f"Latest: {result.latest_path}")
    print("No orders were sent. This is diagnostics only.")


if __name__ == "__main__":
    main()
