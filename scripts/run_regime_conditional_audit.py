"""Audit the volatility-regime-conditioned edge family (read-only).

Builds each instrument's base session strategies AND their high/low volatility
regime variants, then runs the full honest stack on the expanded family:
walk-forward significance, Bonferroni/Benjamini-Hochberg multiple-testing, and
the Deflated-Sharpe / PBO overfitting audit. Answers: "does conditioning on the
volatility regime reveal an edge that survives correction, or just more noise?"

It never imports execution code, never sends orders, never changes config.
Missing CSVs are skipped.
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

from src.analysis.edge_overfitting import align_return_matrix, session_return_series
from src.analysis.multiple_testing import audit_edges
from src.analysis.overfitting import overfitting_report
from src.analysis.regime_conditioning import conditional_return_series
from src.analysis.session_edge_lab import evaluate_net_returns
from src.data_feed.market_data import load_csv_data


DEFAULT_CONFIG_PATH = Path("config/edge_lab.yaml")
DEFAULT_OUTPUT_DIR = Path("reports/diagnostics")
DEFAULT_DETAIL_CSV = "regime_conditional_detail.csv"
DEFAULT_SUMMARY_CSV = "regime_conditional_summary.csv"
DEFAULT_LATEST_TXT = "regime_conditional_latest.txt"

SUMMARY_COLUMNS = (
    "status",
    "family_size",
    "walk_forward_robust",
    "mtc_survivors",
    "deflated_sharpe_ratio",
    "probability_of_backtest_overfitting",
    "best_strategy",
    "best_sharpe",
    "live_armed",
)


@dataclass(frozen=True)
class RegimeAuditResult:
    status: str
    reason: str
    detail_path: Path
    summary_path: Path
    latest_path: Path


def _build_family(config: dict) -> dict[str, pd.Series]:
    """Base session strategies + their volatility-regime variants, all instruments."""
    family: dict[str, pd.Series] = {}
    for instrument in config.get("instruments", []):
        symbol = str(instrument.get("symbol", "?"))
        csv_path = Path(instrument.get("csv", ""))
        cost = float(instrument.get("cost_per_trade", 0.0))
        if not csv_path.exists():
            continue
        try:
            data = load_csv_data(csv_path)
        except Exception:  # noqa: BLE001
            continue
        family.update(session_return_series(data, symbol, cost_per_trade=cost))
        family.update(conditional_return_series(data, symbol, cost_per_trade=cost))
    return family


def run_regime_conditional_audit(
    *,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    n_splits: int = 14,
) -> RegimeAuditResult:
    paths = _paths(output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    try:
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        return _write_empty(paths, "ERROR", str(exc))

    if not config.get("instruments"):
        return _write_empty(paths, "ERROR", "no instruments configured")

    min_trades = int(config.get("min_trades", 40))
    oos_fraction = float(config.get("oos_fraction", 0.30))
    t_stat_threshold = float(config.get("t_stat_threshold", 1.5))

    family = _build_family(config)
    if len(family) < 2:
        return _write_empty(paths, "INSUFFICIENT_DATA", "fewer than 2 strategies")

    rows = []
    for name, series in family.items():
        metrics = evaluate_net_returns(
            series.to_numpy(), min_trades=min_trades,
            oos_fraction=oos_fraction, t_stat_threshold=t_stat_threshold,
        )
        rows.append({"strategy": name, **metrics})
    detail = audit_edges(pd.DataFrame(rows), t_col="oos_t_stat")

    names, matrix = align_return_matrix(family)
    of_report = overfitting_report(matrix, n_splits=n_splits) if matrix.size else {"status": "INSUFFICIENT_DATA"}

    summary = {
        "status": "OK",
        "family_size": int(len(detail)),
        "walk_forward_robust": int(detail["robust_edge"].sum()) if "robust_edge" in detail else 0,
        "mtc_survivors": int(detail["mtc_robust"].sum()) if "mtc_robust" in detail else 0,
        "deflated_sharpe_ratio": of_report.get("deflated_sharpe_ratio"),
        "probability_of_backtest_overfitting": of_report.get("probability_of_backtest_overfitting"),
        "best_strategy": names[of_report["best_strategy_index"]] if of_report.get("best_strategy_index") is not None and names else None,
        "best_sharpe": of_report.get("best_sharpe"),
        "live_armed": False,
    }
    _write_reports(paths, detail, summary)
    return RegimeAuditResult("OK", "OK", paths["detail"], paths["summary"], paths["latest"])


def _write_reports(paths: dict[str, Path], detail: pd.DataFrame, summary: dict) -> None:
    detail.to_csv(paths["detail"], index=False)
    pd.DataFrame([{col: summary.get(col) for col in SUMMARY_COLUMNS}], columns=SUMMARY_COLUMNS).to_csv(
        paths["summary"], index=False
    )
    paths["latest"].write_text(_build_latest_text(detail, summary), encoding="utf-8")


def _build_latest_text(detail: pd.DataFrame, summary: dict) -> str:
    survivors = detail[detail["mtc_robust"]] if "mtc_robust" in detail else detail.iloc[0:0]
    lines = [
        "Volatility-Regime Conditional Edge Audit",
        "=" * 72,
        f"Status: {summary.get('status')}",
        f"Family size (base + regime variants): {summary.get('family_size')}",
        f"Walk-forward robust: {summary.get('walk_forward_robust')}",
        f"Multiple-testing survivors (mtc_robust): {summary.get('mtc_survivors')}",
        f"Deflated Sharpe Ratio: {summary.get('deflated_sharpe_ratio')}",
        f"Probability of Backtest Overfitting: {summary.get('probability_of_backtest_overfitting')}",
        "",
    ]
    if not survivors.empty:
        lines.append("Survivors (survive walk-forward + multiple-testing):")
        for _, row in survivors.iterrows():
            lines.append(f"  {row['strategy']:<34} oos_t={row['oos_t_stat']:>6} p={row['p_value']:>8}")
    else:
        lines.append("Survivors: NONE — conditioning on volatility did not reveal a robust edge.")
    lines += [
        "",
        "Conditioning grows the hypothesis count, so the multiple-testing and DSR",
        "bars rise accordingly. A survivor here would still need the Monte Carlo and",
        "live-safe checks before any demo. Research only. No orders were sent.",
        "",
    ]
    return "\n".join(lines) + "\n"


def _paths(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    directory = Path(output_dir)
    return {
        "detail": directory / DEFAULT_DETAIL_CSV,
        "summary": directory / DEFAULT_SUMMARY_CSV,
        "latest": directory / DEFAULT_LATEST_TXT,
    }


def _write_empty(paths: dict[str, Path], status: str, reason: str) -> RegimeAuditResult:
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame().to_csv(paths["detail"], index=False)
    pd.DataFrame(columns=SUMMARY_COLUMNS).to_csv(paths["summary"], index=False)
    paths["latest"].write_text(
        "\n".join(
            ["Volatility-Regime Conditional Edge Audit", "=" * 72, f"Status: {status}",
             f"Reason: {reason}", "No orders were sent. This is diagnostics only.", ""]
        ),
        encoding="utf-8",
    )
    return RegimeAuditResult(status, reason, paths["detail"], paths["summary"], paths["latest"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--n-splits", type=int, default=14)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_regime_conditional_audit(config_path=args.config, output_dir=args.output_dir, n_splits=args.n_splits)
    print("=" * 72)
    print("XAU Auto Trader - Volatility-Regime Conditional Edge Audit")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Detail: {result.detail_path}")
    print(f"Summary: {result.summary_path}")
    print(f"Latest: {result.latest_path}")
    print("No orders were sent. This is diagnostics only.")


if __name__ == "__main__":
    main()
