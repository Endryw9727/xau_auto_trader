"""Test the pre-registered overnight/intraday anomaly across instruments.

Single theory-driven hypothesis (two fixed legs per instrument), so the
multiple-testing family is small. Evaluates each leg walk-forward + net of cost,
then applies the same multiple-testing correction over this small family. Reports
which (if any) instruments show a corrected-significant overnight effect.

Reuses config/edge_lab.yaml. Never imports execution code, never sends orders.
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
from src.analysis.overnight_anomaly import evaluate_overnight_anomaly
from src.data_feed.market_data import load_csv_data


DEFAULT_CONFIG_PATH = Path("config/edge_lab.yaml")
DEFAULT_OUTPUT_DIR = Path("reports/diagnostics")
DEFAULT_AUDIT_CSV = "overnight_anomaly_audit.csv"
DEFAULT_LATEST_TXT = "overnight_anomaly_latest.txt"

FAMILY_COLUMNS = ("symbol", "leg", "trades", "is_t_stat", "oos_t_stat", "mean_net_pct", "robust_edge")


@dataclass(frozen=True)
class OvernightAnomalyResult:
    status: str
    reason: str
    audit_path: Path
    latest_path: Path


def run_overnight_anomaly(
    *,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    alpha: float = 0.05,
) -> OvernightAnomalyResult:
    paths = overnight_paths(output_dir)
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

    rows = []
    for instrument in instruments:
        symbol = str(instrument.get("symbol", "?"))
        csv_path = Path(instrument.get("csv", ""))
        cost = float(instrument.get("cost_per_trade", 0.0))
        if not csv_path.exists():
            continue
        try:
            data = load_csv_data(csv_path)
            edges = evaluate_overnight_anomaly(
                data, cost_per_trade=cost, min_trades=min_trades,
                oos_fraction=oos_fraction, t_stat_threshold=t_stat_threshold,
            )
        except Exception:  # noqa: BLE001
            continue
        for _, row in edges.iterrows():
            rows.append(
                {
                    "symbol": symbol, "leg": str(row["leg"]), "trades": int(row["trades"]),
                    "is_t_stat": float(row["is_t_stat"]), "oos_t_stat": float(row["oos_t_stat"]),
                    "mean_net_pct": float(row["mean_net_pct"]), "robust_edge": bool(row["robust_edge"]),
                }
            )

    family = pd.DataFrame(rows, columns=FAMILY_COLUMNS)
    if family.empty:
        return _write_empty(paths, "NO_DATA", "no instrument data available")

    audited = audit_edges(family, t_col="oos_t_stat", alpha=alpha)
    audited.to_csv(paths["audit"], index=False)
    paths["latest"].write_text(_build_latest_text(audited, alpha), encoding="utf-8")
    return OvernightAnomalyResult("OK", "overnight anomaly audit completed", paths["audit"], paths["latest"])


def _build_latest_text(audited: pd.DataFrame, alpha: float) -> str:
    survivors = audited[audited["mtc_robust"]] if "mtc_robust" in audited.columns else audited.iloc[0:0]
    robust = audited[audited["robust_edge"]] if "robust_edge" in audited.columns else audited.iloc[0:0]
    lines = [
        "Overnight/Intraday Anomaly (pre-registered)",
        "=" * 72,
        f"Family size (small, theory-driven): {len(audited)}",
        f"Walk-forward robust: {len(robust)}",
        f"Survive correction (mtc_robust): {len(survivors)}",
        f"alpha: {alpha}",
        "",
        "All legs",
        "-" * 72,
    ]
    for _, row in audited.sort_values("oos_t_stat", key=lambda s: s.abs(), ascending=False).iterrows():
        lines.append(
            f"{row['symbol']:<8} | {row['leg']:<15} | trades={int(row['trades']):<5} | "
            f"oos_t={row['oos_t_stat']:.2f} | mean%={row['mean_net_pct']:.4f} | "
            f"p={row['p_value']:.4f} | bh={bool(row['bh_significant'])} | mtc_robust={bool(row['mtc_robust'])}"
        )
    lines += [
        "",
        "Pre-registered legs (theory: overnight positive, intraday negative).",
        "Research only. No orders were sent.",
        "",
    ]
    return "\n".join(lines) + "\n"


def overnight_paths(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    directory = Path(output_dir)
    return {"audit": directory / DEFAULT_AUDIT_CSV, "latest": directory / DEFAULT_LATEST_TXT}


def _write_empty(paths: dict[str, Path], status: str, reason: str) -> OvernightAnomalyResult:
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=FAMILY_COLUMNS).to_csv(paths["audit"], index=False)
    paths["latest"].write_text(
        "\n".join(["Overnight/Intraday Anomaly (pre-registered)", "=" * 72, f"Status: {status}",
                   f"Reason: {reason}", "No orders were sent. This is diagnostics only.", ""]),
        encoding="utf-8",
    )
    return OvernightAnomalyResult(status, reason, paths["audit"], paths["latest"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Edge lab config path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Report output directory.")
    parser.add_argument("--alpha", type=float, default=0.05, help="Family-wise / FDR alpha.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_overnight_anomaly(config_path=args.config, output_dir=args.output_dir, alpha=args.alpha)
    print("=" * 72)
    print("XAU Auto Trader - Overnight/Intraday Anomaly")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print(f"Audit: {result.audit_path}")
    print(f"Latest: {result.latest_path}")
    print("No orders were sent. This is diagnostics only.")


if __name__ == "__main__":
    main()
