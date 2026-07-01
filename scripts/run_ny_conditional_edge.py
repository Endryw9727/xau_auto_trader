"""Scan instruments for a conditional New York session edge (research only).

Reuses config/edge_lab.yaml. For each instrument it tests whether trading the NY
session conditioned on the pre-NY (Asia+London) direction has a robust,
cost-adjusted, out-of-sample edge (continuation or reversal). Flags the robust
(symbol, condition, direction) combinations and marks instruments with none as
EXCLUDE.

Never imports execution code, never sends orders, never changes config. Missing
CSVs are skipped as NO_DATA.
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

from src.analysis.ny_conditional_edge import NY_EDGE_COLUMNS, evaluate_ny_conditional_edges
from src.data_feed.market_data import load_csv_data


DEFAULT_CONFIG_PATH = Path("config/edge_lab.yaml")
DEFAULT_OUTPUT_DIR = Path("reports/diagnostics")
DEFAULT_VERDICT_CSV = "ny_conditional_verdicts.csv"
DEFAULT_DETAIL_CSV = "ny_conditional_detail.csv"
DEFAULT_LATEST_TXT = "ny_conditional_latest.txt"

VERDICT_COLUMNS = (
    "symbol",
    "status",
    "verdict",
    "best_condition",
    "best_direction",
    "best_hypothesis",
    "best_oos_t_stat",
    "best_mean_net_pct",
    "robust_edges",
    "note",
)


@dataclass(frozen=True)
class NyConditionalResult:
    status: str
    reason: str
    verdict_path: Path
    detail_path: Path
    latest_path: Path


def run_ny_conditional_edge(
    *,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> NyConditionalResult:
    paths = ny_conditional_paths(output_dir)
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

    verdict_rows = []
    detail_frames = []
    for instrument in instruments:
        symbol = str(instrument.get("symbol", "?"))
        csv_path = Path(instrument.get("csv", ""))
        cost = float(instrument.get("cost_per_trade", 0.0))
        if not csv_path.exists():
            verdict_rows.append(_verdict_row(symbol, "NO_DATA", None, note=f"missing {csv_path}"))
            continue
        try:
            data = load_csv_data(csv_path)
            edges = evaluate_ny_conditional_edges(
                data, cost_per_trade=cost, min_trades=min_trades,
                oos_fraction=oos_fraction, t_stat_threshold=t_stat_threshold,
            )
        except Exception as exc:  # noqa: BLE001
            verdict_rows.append(_verdict_row(symbol, "ERROR", None, note=str(exc)))
            continue
        verdict_rows.append(_verdict_row(symbol, "OK", edges))
        if not edges.empty:
            detail = edges.copy()
            detail.insert(0, "symbol", symbol)
            detail_frames.append(detail)

    verdicts = pd.DataFrame(verdict_rows, columns=VERDICT_COLUMNS)
    detail = pd.concat(detail_frames, ignore_index=True) if detail_frames else pd.DataFrame(
        columns=("symbol", *NY_EDGE_COLUMNS)
    )
    verdicts.to_csv(paths["verdict"], index=False)
    detail.to_csv(paths["detail"], index=False)
    paths["latest"].write_text(_build_latest_text(verdicts, detail), encoding="utf-8")
    return NyConditionalResult("OK", "ny conditional edge scan completed", paths["verdict"], paths["detail"], paths["latest"])


def _verdict_row(symbol: str, status: str, edges, *, note: str = "") -> dict:
    if edges is None or (hasattr(edges, "empty") and edges.empty):
        return {
            "symbol": symbol, "status": status, "verdict": "EXCLUDE", "best_condition": "",
            "best_direction": "", "best_hypothesis": "", "best_oos_t_stat": 0.0,
            "best_mean_net_pct": 0.0, "robust_edges": 0, "note": note,
        }
    robust = edges[edges["robust_edge"]].copy()
    if robust.empty:
        return {
            "symbol": symbol, "status": status, "verdict": "EXCLUDE", "best_condition": "",
            "best_direction": "", "best_hypothesis": "", "best_oos_t_stat": 0.0,
            "best_mean_net_pct": 0.0, "robust_edges": 0, "note": note,
        }
    robust["_abs_oos"] = robust["oos_t_stat"].abs()
    best = robust.sort_values("_abs_oos", ascending=False).iloc[0]
    return {
        "symbol": symbol, "status": status, "verdict": "KEEP",
        "best_condition": str(best["condition"]), "best_direction": str(best["direction"]),
        "best_hypothesis": str(best["hypothesis"]), "best_oos_t_stat": round(float(best["oos_t_stat"]), 3),
        "best_mean_net_pct": round(float(best["mean_net_pct"]), 6), "robust_edges": int(len(robust)), "note": note,
    }


def _build_latest_text(verdicts: pd.DataFrame, detail: pd.DataFrame) -> str:
    keep = verdicts[verdicts["verdict"] == "KEEP"]
    lines = [
        "NY Conditional Session Edge",
        "=" * 72,
        f"Instruments scanned: {len(verdicts)}",
        f"KEEP (robust NY conditional edge): {len(keep)}",
        "",
        "Verdicts",
        "-" * 72,
    ]
    for _, row in verdicts.iterrows():
        lines.append(
            f"{row['symbol']:<8} | {row['status']:<8} | {row['verdict']:<8} | "
            f"best={row['best_condition']}/{row['best_direction']}/{row['best_hypothesis']} | "
            f"oos_t={row['best_oos_t_stat']} | mean%={row['best_mean_net_pct']} | {row['note']}"
        )
    robust_detail = detail[detail["robust_edge"]] if not detail.empty else detail
    if not robust_detail.empty:
        lines += ["", "Robust combinations", "-" * 72]
        for _, row in robust_detail.iterrows():
            lines.append(
                f"{row['symbol']} | {row['condition']}/{row['direction']} ({row['hypothesis']}) | "
                f"trades={row['trades']} is_t={row['is_t_stat']} oos_t={row['oos_t_stat']} mean%={row['mean_net_pct']}"
            )
    lines += [
        "",
        "Condition uses only pre-NY (Asia+London) candles: no lookahead. An edge",
        "must be significant in BOTH in-sample and out-of-sample halves, net of",
        "cost. Research only. No orders were sent.",
        "",
    ]
    return "\n".join(lines) + "\n"


def ny_conditional_paths(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    directory = Path(output_dir)
    return {
        "verdict": directory / DEFAULT_VERDICT_CSV,
        "detail": directory / DEFAULT_DETAIL_CSV,
        "latest": directory / DEFAULT_LATEST_TXT,
    }


def _write_empty(paths: dict[str, Path], status: str, reason: str) -> NyConditionalResult:
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=VERDICT_COLUMNS).to_csv(paths["verdict"], index=False)
    pd.DataFrame(columns=("symbol", *NY_EDGE_COLUMNS)).to_csv(paths["detail"], index=False)
    paths["latest"].write_text(
        "\n".join(["NY Conditional Session Edge", "=" * 72, f"Status: {status}", f"Reason: {reason}",
                   "No orders were sent. This is diagnostics only.", ""]),
        encoding="utf-8",
    )
    return NyConditionalResult(status, reason, paths["verdict"], paths["detail"], paths["latest"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Edge lab config path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Report output directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_ny_conditional_edge(config_path=args.config, output_dir=args.output_dir)
    print("=" * 72)
    print("XAU Auto Trader - NY Conditional Session Edge")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print(f"Verdicts: {result.verdict_path}")
    print(f"Detail: {result.detail_path}")
    print(f"Latest: {result.latest_path}")
    print("No orders were sent. This is diagnostics only.")


if __name__ == "__main__":
    main()
