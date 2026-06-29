"""Report-only V51 demo readiness (Phase 3, no execution).

This is the report-only phase that must precede any demo execution. It simulates
how the protective guardrails (per-day trade cap, daily-loss lock, drawdown
lock) would have behaved on the accepted V51 candidates, and prints a read-only
safety checklist confirming that execution stays disabled.

It NEVER enables execution, NEVER changes config or flags, NEVER imports
execution code and NEVER sends orders. Arming demo execution remains a separate,
explicit, manual decision outside this report.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.v51_demo_readiness import (
    DAILY_EQUITY_COLUMNS,
    READINESS_CHECKLIST_COLUMNS,
    build_readiness_checklist,
    evaluate_guardrails,
    simulate_daily_equity,
)
from src.analysis.v51_outcome_simulation import simulate_candidate_outcomes
from src.data_feed.market_data import load_csv_data
from src.strategy_lab.strategy_v51_demo_intraday import (
    DEFAULT_V51_CONFIG_PATH,
    build_demo_intraday_decision_log,
    load_v51_config,
)


DEFAULT_OUTPUT_DIR = Path("reports/diagnostics")
DEFAULT_EQUITY_CSV = "v51_demo_readiness_equity.csv"
DEFAULT_CHECKLIST_CSV = "v51_demo_readiness_checklist.csv"
DEFAULT_LATEST_TXT = "v51_demo_readiness_latest.txt"
DEFAULT_XAUUSD_CSV_PATH = Path("data/raw/xauusd.csv")


@dataclass(frozen=True)
class V51DemoReadinessResult:
    """Status and paths for one generated demo-readiness report."""

    status: str
    reason: str
    equity_path: Path
    checklist_path: Path
    latest_path: Path


def run_v51_demo_readiness_report(
    *,
    candles: int = 800,
    max_horizon_candles: int = 32,
    daily_loss_limit_r: float = 2.0,
    max_drawdown_r: float = 4.0,
    config_path: str | Path = DEFAULT_V51_CONFIG_PATH,
    csv_path: str | Path = DEFAULT_XAUUSD_CSV_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> V51DemoReadinessResult:
    """Generate the report-only V51 demo readiness report."""
    if candles <= 0:
        raise ValueError("candles must be positive")

    paths = readiness_paths(output_dir)
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

    checklist = build_readiness_checklist(config)
    working_data = data.tail(config.warmup_candles + candles).copy()
    decision_log = build_demo_intraday_decision_log(working_data, config, enforce_daily_limit=False)
    outcomes = simulate_candidate_outcomes(decision_log, working_data, max_horizon_candles=max_horizon_candles)

    equity = simulate_daily_equity(
        outcomes, max_trades_per_day=config.max_trades_per_day, daily_loss_limit_r=daily_loss_limit_r
    )
    evaluation = evaluate_guardrails(
        outcomes,
        max_trades_per_day=config.max_trades_per_day,
        daily_loss_limit_r=daily_loss_limit_r,
        max_drawdown_r=max_drawdown_r,
    )

    equity.to_csv(paths["equity"], index=False)
    checklist.to_csv(paths["checklist"], index=False)
    paths["latest"].write_text(
        _build_latest_text(checklist, evaluation, daily_loss_limit_r, max_drawdown_r, config), encoding="utf-8"
    )
    return V51DemoReadinessResult(
        "OK", "V51 demo readiness report generated", paths["equity"], paths["checklist"], paths["latest"]
    )


def _build_latest_text(checklist, evaluation, daily_loss_limit_r, max_drawdown_r, config) -> str:
    all_ok = bool((checklist["status"] == "OK").all())
    lines = [
        "V51 Demo Readiness (REPORT ONLY)",
        "=" * 72,
        "Execution is NOT armed by this report. Arming demo execution is a",
        "separate, explicit, manual decision.",
        "",
        "Safety checklist",
        "-" * 72,
    ]
    for _, row in checklist.iterrows():
        lines.append(f"{row['check']} = {row['value']} (expected {row['expected']}) -> {row['status']}")
    lines += [
        f"Execution gates all safe: {all_ok}",
        "",
        "Guardrail simulation on ACCEPTED candidates (theoretical)",
        "-" * 72,
        f"max_trades_per_day (from config): {config.max_trades_per_day}",
        f"daily_loss_limit_r (report param): {daily_loss_limit_r}",
        f"max_drawdown_r (report param): {max_drawdown_r}",
        f"trading_days: {evaluation.trading_days}",
        f"total_trades_taken: {evaluation.total_trades}",
        f"trades_skipped_by_cap_or_lock: {evaluation.capped_trades}",
        f"total_r: {evaluation.total_r}",
        f"max_drawdown_r: {evaluation.max_drawdown_r}",
        f"worst_day_r: {evaluation.worst_day_r}",
        f"daily_loss_lock_days: {evaluation.daily_loss_lock_days}",
        f"drawdown_lock_would_trigger: {evaluation.drawdown_lock_hit}",
        "",
        "Note: theoretical metrics on the full historical decision log. This",
        "report does not authorize execution and changes no config.",
        "No orders were sent. This is diagnostics only.",
        "",
    ]
    return "\n".join(lines) + "\n"


def readiness_paths(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    """Return output paths for the demo-readiness report."""
    directory = Path(output_dir)
    return {
        "equity": directory / DEFAULT_EQUITY_CSV,
        "checklist": directory / DEFAULT_CHECKLIST_CSV,
        "latest": directory / DEFAULT_LATEST_TXT,
    }


def _write_empty(paths: dict[str, Path], status: str, reason: str) -> V51DemoReadinessResult:
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=DAILY_EQUITY_COLUMNS).to_csv(paths["equity"], index=False)
    pd.DataFrame(columns=READINESS_CHECKLIST_COLUMNS).to_csv(paths["checklist"], index=False)
    paths["latest"].write_text(
        "\n".join(
            [
                "V51 Demo Readiness (REPORT ONLY)",
                "=" * 72,
                f"Status: {status}",
                f"Reason: {reason}",
                "Execution is NOT armed by this report.",
                "No orders were sent. This is diagnostics only.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return V51DemoReadinessResult(status, reason, paths["equity"], paths["checklist"], paths["latest"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candles", type=int, default=800, help="Latest closed candles to evaluate.")
    parser.add_argument("--horizon", type=int, default=32, help="Max candles to hold each simulated trade.")
    parser.add_argument("--daily-loss-limit-r", type=float, default=2.0, help="Daily-loss lock budget in R.")
    parser.add_argument("--max-drawdown-r", type=float, default=4.0, help="Drawdown lock budget in R.")
    parser.add_argument("--config", type=Path, default=DEFAULT_V51_CONFIG_PATH, help="V51 config path.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_XAUUSD_CSV_PATH, help="Local OHLCV CSV path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Report output directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_v51_demo_readiness_report(
        candles=args.candles,
        max_horizon_candles=args.horizon,
        daily_loss_limit_r=args.daily_loss_limit_r,
        max_drawdown_r=args.max_drawdown_r,
        config_path=args.config,
        csv_path=args.csv,
        output_dir=args.output_dir,
    )
    print("=" * 72)
    print("XAU Auto Trader - V51 Demo Readiness (REPORT ONLY)")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print(f"Equity: {result.equity_path}")
    print(f"Checklist: {result.checklist_path}")
    print(f"Latest: {result.latest_path}")
    print("Execution is NOT armed by this report. No orders were sent.")


if __name__ == "__main__":
    main()
