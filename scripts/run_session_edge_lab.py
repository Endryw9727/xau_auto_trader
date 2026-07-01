"""Scan multiple instruments for a session drift edge and report KEEP/EXCLUDE.

Reads config/edge_lab.yaml (instruments + local CSV paths + realistic costs),
runs the read-only session edge lab on each instrument that has data, and writes
a per-instrument verdict plus a combined ranking. Instruments without a robust,
cost-adjusted, out-of-sample edge are flagged EXCLUDE.

It never imports execution code, never sends orders and never changes config.
Missing CSVs are skipped with a NO_DATA status, not an error.
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

from src.analysis.session_edge_lab import EDGE_COLUMNS, evaluate_session_edges, symbol_edge_verdict
from src.data_feed.market_data import load_csv_data


DEFAULT_CONFIG_PATH = Path("config/edge_lab.yaml")
DEFAULT_OUTPUT_DIR = Path("reports/diagnostics")
DEFAULT_VERDICT_CSV = "session_edge_verdicts.csv"
DEFAULT_DETAIL_CSV = "session_edge_detail.csv"
DEFAULT_LATEST_TXT = "session_edge_latest.txt"

VERDICT_COLUMNS = (
    "symbol",
    "status",
    "verdict",
    "best_session",
    "best_direction",
    "best_oos_t_stat",
    "best_oos_mean_pct",
    "robust_edges",
    "note",
)


@dataclass(frozen=True)
class SessionEdgeLabResult:
    status: str
    reason: str
    verdict_path: Path
    detail_path: Path
    latest_path: Path


def run_session_edge_lab(
    *,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> SessionEdgeLabResult:
    """Run the multi-instrument session edge scan."""
    paths = edge_lab_paths(output_dir)
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
            edges = evaluate_session_edges(
                data,
                cost_per_trade=cost,
                min_trades=min_trades,
                oos_fraction=oos_fraction,
                t_stat_threshold=t_stat_threshold,
            )
        except Exception as exc:  # noqa: BLE001
            verdict_rows.append(_verdict_row(symbol, "ERROR", None, note=str(exc)))
            continue
        verdict = symbol_edge_verdict(symbol, edges)
        verdict_rows.append(_verdict_row(symbol, "OK", verdict))
        if not edges.empty:
            detail = edges.copy()
            detail.insert(0, "symbol", symbol)
            detail_frames.append(detail)

    verdicts = pd.DataFrame(verdict_rows, columns=VERDICT_COLUMNS)
    detail = pd.concat(detail_frames, ignore_index=True) if detail_frames else pd.DataFrame(
        columns=("symbol", *EDGE_COLUMNS)
    )
    verdicts.to_csv(paths["verdict"], index=False)
    detail.to_csv(paths["detail"], index=False)
    paths["latest"].write_text(_build_latest_text(verdicts), encoding="utf-8")
    return SessionEdgeLabResult("OK", "session edge lab completed", paths["verdict"], paths["detail"], paths["latest"])


def _verdict_row(symbol: str, status: str, verdict, *, note: str = "") -> dict:
    if verdict is None:
        return {
            "symbol": symbol, "status": status, "verdict": "EXCLUDE", "best_session": "",
            "best_direction": "", "best_oos_t_stat": 0.0, "best_oos_mean_pct": 0.0,
            "robust_edges": 0, "note": note,
        }
    return {
        "symbol": symbol,
        "status": status,
        "verdict": verdict.verdict,
        "best_session": verdict.best_session,
        "best_direction": verdict.best_direction,
        "best_oos_t_stat": round(verdict.best_oos_t_stat, 3),
        "best_oos_mean_pct": round(verdict.best_oos_mean_pct, 6),
        "robust_edges": verdict.robust_edges,
        "note": note,
    }


def _build_latest_text(verdicts: pd.DataFrame) -> str:
    keep = verdicts[verdicts["verdict"] == "KEEP"]
    exclude = verdicts[verdicts["verdict"] == "EXCLUDE"]
    lines = [
        "Multi-Instrument Session Edge Lab",
        "=" * 72,
        f"Instruments scanned: {len(verdicts)}",
        f"KEEP (robust out-of-sample edge): {len(keep)}",
        f"EXCLUDE (no robust edge / no data): {len(exclude)}",
        "",
        "Verdicts",
        "-" * 72,
    ]
    for _, row in verdicts.iterrows():
        lines.append(
            f"{row['symbol']:<8} | {row['status']:<8} | {row['verdict']:<8} | "
            f"best={row['best_session']}/{row['best_direction']} | "
            f"oos_t={row['best_oos_t_stat']} | oos_mean%={row['best_oos_mean_pct']} | {row['note']}"
        )
    lines += [
        "",
        "Method: enter at session open, exit at session close; net of cost; an edge",
        "must be significant (|t|>=threshold, same sign) in BOTH in-sample and",
        "out-of-sample halves. This is research only. No orders were sent.",
        "",
    ]
    return "\n".join(lines) + "\n"


def edge_lab_paths(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    directory = Path(output_dir)
    return {
        "verdict": directory / DEFAULT_VERDICT_CSV,
        "detail": directory / DEFAULT_DETAIL_CSV,
        "latest": directory / DEFAULT_LATEST_TXT,
    }


def _write_empty(paths: dict[str, Path], status: str, reason: str) -> SessionEdgeLabResult:
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=VERDICT_COLUMNS).to_csv(paths["verdict"], index=False)
    pd.DataFrame(columns=("symbol", *EDGE_COLUMNS)).to_csv(paths["detail"], index=False)
    paths["latest"].write_text(
        "\n".join(
            ["Multi-Instrument Session Edge Lab", "=" * 72, f"Status: {status}", f"Reason: {reason}",
             "No orders were sent. This is diagnostics only.", ""]
        ),
        encoding="utf-8",
    )
    return SessionEdgeLabResult(status, reason, paths["verdict"], paths["detail"], paths["latest"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Edge lab config path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Report output directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_session_edge_lab(config_path=args.config, output_dir=args.output_dir)
    print("=" * 72)
    print("XAU Auto Trader - Multi-Instrument Session Edge Lab")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print(f"Verdicts: {result.verdict_path}")
    print(f"Detail: {result.detail_path}")
    print(f"Latest: {result.latest_path}")
    print("No orders were sent. This is diagnostics only.")


if __name__ == "__main__":
    main()
