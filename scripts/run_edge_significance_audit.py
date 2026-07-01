"""Audit all candidate edges for multiple-testing significance (research only).

Re-runs the session edge lab and the NY conditional edge across every configured
instrument, gathers the whole family of tested hypotheses, and applies Bonferroni
and Benjamini-Hochberg corrections to the out-of-sample t-stats. An edge is only
trusted (mtc_robust) if it is walk-forward robust AND survives FDR correction for
how many hypotheses were tried.

Never imports execution code, never sends orders, never changes config.
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

from src.analysis.multiple_testing import audit_edges
from src.analysis.ny_conditional_edge import evaluate_ny_conditional_edges
from src.analysis.session_edge_lab import evaluate_session_edges
from src.data_feed.market_data import load_csv_data


DEFAULT_CONFIG_PATH = Path("config/edge_lab.yaml")
DEFAULT_OUTPUT_DIR = Path("reports/diagnostics")
DEFAULT_AUDIT_CSV = "edge_significance_audit.csv"
DEFAULT_LATEST_TXT = "edge_significance_latest.txt"

FAMILY_COLUMNS = ("symbol", "source", "combo", "trades", "is_t_stat", "oos_t_stat", "mean_net_pct", "robust_edge")


@dataclass(frozen=True)
class EdgeAuditResult:
    status: str
    reason: str
    audit_path: Path
    latest_path: Path


def run_edge_significance_audit(
    *,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    alpha: float = 0.05,
) -> EdgeAuditResult:
    paths = audit_paths(output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    try:
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        return _write_empty(paths, "ERROR", str(exc))

    instruments = config.get("instruments", [])
    if not instruments:
        return _write_empty(paths, "ERROR", "no instruments configured")
    min_trades = int(config.get("min_trades", 40))
    oos_fraction = float(config.get("oos_fraction", 0.30))
    t_stat_threshold = float(config.get("t_stat_threshold", 1.5))

    family = _collect_family(instruments, min_trades, oos_fraction, t_stat_threshold)
    if family.empty:
        return _write_empty(paths, "NO_DATA", "no instrument data available to audit")

    audited = audit_edges(family, t_col="oos_t_stat", alpha=alpha)
    audited.to_csv(paths["audit"], index=False)
    paths["latest"].write_text(_build_latest_text(audited, alpha), encoding="utf-8")
    return EdgeAuditResult("OK", "edge significance audit completed", paths["audit"], paths["latest"])


def _collect_family(instruments, min_trades, oos_fraction, t_stat_threshold) -> pd.DataFrame:
    rows = []
    for instrument in instruments:
        symbol = str(instrument.get("symbol", "?"))
        csv_path = Path(instrument.get("csv", ""))
        cost = float(instrument.get("cost_per_trade", 0.0))
        if not csv_path.exists():
            continue
        try:
            data = load_csv_data(csv_path)
        except Exception:  # noqa: BLE001
            continue
        session = evaluate_session_edges(
            data, cost_per_trade=cost, min_trades=min_trades, oos_fraction=oos_fraction, t_stat_threshold=t_stat_threshold
        )
        for _, row in session.iterrows():
            rows.append(_family_row(symbol, "session", f"{row['session']}/{row['direction']}", row))
        ny = evaluate_ny_conditional_edges(
            data, cost_per_trade=cost, min_trades=min_trades, oos_fraction=oos_fraction, t_stat_threshold=t_stat_threshold
        )
        for _, row in ny.iterrows():
            combo = f"{row['condition']}/{row['direction']}/{row['hypothesis']}"
            rows.append(_family_row(symbol, "ny_cond", combo, row))
    return pd.DataFrame(rows, columns=FAMILY_COLUMNS)


def _family_row(symbol: str, source: str, combo: str, row) -> dict:
    return {
        "symbol": symbol,
        "source": source,
        "combo": combo,
        "trades": int(row["trades"]),
        "is_t_stat": float(row["is_t_stat"]),
        "oos_t_stat": float(row["oos_t_stat"]),
        "mean_net_pct": float(row["mean_net_pct"]),
        "robust_edge": bool(row["robust_edge"]),
    }


def _build_latest_text(audited: pd.DataFrame, alpha: float) -> str:
    family_size = int(len(audited))
    walk_forward = audited[audited["robust_edge"]] if "robust_edge" in audited.columns else audited.iloc[0:0]
    survivors = audited[audited["mtc_robust"]] if "mtc_robust" in audited.columns else audited.iloc[0:0]
    lines = [
        "Edge Significance Audit (multiple-testing)",
        "=" * 72,
        f"Hypotheses tested (family size): {family_size}",
        f"Walk-forward robust (pre-correction): {int(len(walk_forward))}",
        f"Survive FDR correction (mtc_robust): {int(len(survivors))}",
        f"alpha: {alpha}",
        "",
        "Walk-forward robust candidates and whether they survive correction",
        "-" * 72,
    ]
    if walk_forward.empty:
        lines.append("(no walk-forward robust candidates)")
    for _, row in walk_forward.sort_values("oos_t_stat", key=lambda s: s.abs(), ascending=False).iterrows():
        lines.append(
            f"{row['symbol']:<8} | {row['source']:<8} | {row['combo']:<26} | "
            f"oos_t={row['oos_t_stat']:.2f} | p={row['p_value']:.4f} | "
            f"bonferroni={bool(row['bonferroni_significant'])} | bh={bool(row['bh_significant'])} | "
            f"mtc_robust={bool(row['mtc_robust'])}"
        )
    lines += [
        "",
        "Interpretation: an edge that is walk-forward robust but does NOT survive",
        "correction is a weak candidate likely inflated by how many hypotheses were",
        "tried. Only mtc_robust edges deserve promotion to paper/forward testing.",
        "Research only. No orders were sent.",
        "",
    ]
    return "\n".join(lines) + "\n"


def audit_paths(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    directory = Path(output_dir)
    return {"audit": directory / DEFAULT_AUDIT_CSV, "latest": directory / DEFAULT_LATEST_TXT}


def _write_empty(paths: dict[str, Path], status: str, reason: str) -> EdgeAuditResult:
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=FAMILY_COLUMNS).to_csv(paths["audit"], index=False)
    paths["latest"].write_text(
        "\n".join(["Edge Significance Audit (multiple-testing)", "=" * 72, f"Status: {status}",
                   f"Reason: {reason}", "No orders were sent. This is diagnostics only.", ""]),
        encoding="utf-8",
    )
    return EdgeAuditResult(status, reason, paths["audit"], paths["latest"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Edge lab config path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Report output directory.")
    parser.add_argument("--alpha", type=float, default=0.05, help="Family-wise / FDR alpha.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_edge_significance_audit(config_path=args.config, output_dir=args.output_dir, alpha=args.alpha)
    print("=" * 72)
    print("XAU Auto Trader - Edge Significance Audit")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print(f"Audit: {result.audit_path}")
    print(f"Latest: {result.latest_path}")
    print("No orders were sent. This is diagnostics only.")


if __name__ == "__main__":
    main()
