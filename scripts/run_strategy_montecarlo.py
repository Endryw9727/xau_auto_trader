"""Bootstrap Monte Carlo of every edge strategy's next N trades (read-only).

Reads config/edge_lab.yaml, rebuilds each instrument's session/direction strategy
return series, and for each strategy resamples its realised trades into thousands
of possible sequences. Reports, per strategy: realised win rate, reward:risk,
expectancy, probability of profit, expected drawdown and probability of ruin.

Answers "over the next 100 trades, is this strategy likely profitable and how
risky is it?" It never imports execution code, never sends orders, never changes
config. Missing CSVs are skipped.
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

from src.analysis.edge_overfitting import session_return_series
from src.analysis.strategy_montecarlo import STRATEGY_MC_COLUMNS, montecarlo_summary, strategy_outcome_table
from src.data_feed.market_data import load_csv_data


DEFAULT_CONFIG_PATH = Path("config/edge_lab.yaml")
DEFAULT_OUTPUT_DIR = Path("reports/diagnostics")
DEFAULT_TABLE_CSV = "strategy_montecarlo.csv"
DEFAULT_SUMMARY_CSV = "strategy_montecarlo_summary.csv"
DEFAULT_LATEST_TXT = "strategy_montecarlo_latest.txt"

SUMMARY_COLUMNS = (
    "status",
    "n_strategies",
    "n_profitable",
    "best_strategy",
    "best_prob_profit",
    "best_expectancy_r",
    "live_armed",
)


@dataclass(frozen=True)
class StrategyMonteCarloResult:
    status: str
    reason: str
    table_path: Path
    summary_path: Path
    latest_path: Path


def run_strategy_montecarlo(
    *,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    n_sims: int = 1000,
    n_trades: int = 100,
    seed: int = 0,
) -> StrategyMonteCarloResult:
    """Per-strategy bootstrap Monte Carlo across all configured instruments."""
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
        except Exception:  # noqa: BLE001 - skip an unreadable instrument
            continue

    rows = strategy_outcome_table(series_by_strategy, n_sims=n_sims, n_trades=n_trades, seed=seed)
    summary = montecarlo_summary(rows)
    _write_reports(paths, rows, summary, n_trades=n_trades)
    return StrategyMonteCarloResult("OK", summary.get("status", "OK"), paths["table"], paths["summary"], paths["latest"])


def _write_reports(paths: dict[str, Path], rows: list[dict], summary: dict, *, n_trades: int) -> None:
    pd.DataFrame(rows, columns=STRATEGY_MC_COLUMNS).to_csv(paths["table"], index=False)
    summary_row = {col: summary.get(col) for col in SUMMARY_COLUMNS}
    summary_row["status"] = summary.get("status", "OK")
    summary_row["live_armed"] = False
    pd.DataFrame([summary_row], columns=SUMMARY_COLUMNS).to_csv(paths["summary"], index=False)
    paths["latest"].write_text(_build_latest_text(rows, summary, n_trades=n_trades), encoding="utf-8")


def _build_latest_text(rows: list[dict], summary: dict, *, n_trades: int) -> str:
    lines = [
        "Per-Strategy Monte Carlo (bootstrap of realised trades)",
        "=" * 72,
        f"Status: {summary.get('status', 'OK')}",
        f"Strategies evaluated: {summary.get('n_strategies', 0)}",
        f"Profitable (E>0 and P(profit)>=50%): {summary.get('n_profitable', 0)}",
        f"Horizon: {n_trades} trades per simulation",
        "",
        f"{'strategy':<26} {'trades':>7} {'win%':>6} {'R:R':>6} {'E(R)':>7} {'P(profit)':>9} {'medDD':>7} {'P(ruin)':>8}",
        "-" * 82,
    ]
    for row in rows[:15]:
        lines.append(
            f"{row['strategy']:<26} {row['trades']:>7} {row['win_rate']*100:>5.1f} "
            f"{row['reward_risk']:>6.2f} {row['expectancy_r']:>7.3f} "
            f"{row['prob_profit']*100:>8.1f}% {row['median_max_drawdown']*100:>6.1f}% "
            f"{row['prob_ruin']*100:>7.1f}%"
        )
    lines += [
        "",
        "P(profit) = share of simulated sequences ending above start. medDD = median",
        "worst drawdown. P(ruin) = share losing >=50% peak-to-trough. Realised R:R and",
        "win% describe the raw session move (no designed stop/target).",
        "",
        "IMPORTANT: this resamples the FULL in-sample history, so it describes the",
        "variance of an edge *assuming it is real*. It does NOT prove the edge exists.",
        "Trust these numbers only for strategies that already survive the walk-forward",
        "+ multiple-testing and the Deflated-Sharpe / PBO overfitting audit. Research",
        "only. No orders were sent.",
        "",
    ]
    return "\n".join(lines) + "\n"


def _paths(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    directory = Path(output_dir)
    return {
        "table": directory / DEFAULT_TABLE_CSV,
        "summary": directory / DEFAULT_SUMMARY_CSV,
        "latest": directory / DEFAULT_LATEST_TXT,
    }


def _write_empty(paths: dict[str, Path], status: str, reason: str) -> StrategyMonteCarloResult:
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=STRATEGY_MC_COLUMNS).to_csv(paths["table"], index=False)
    pd.DataFrame(columns=SUMMARY_COLUMNS).to_csv(paths["summary"], index=False)
    paths["latest"].write_text(
        "\n".join(
            ["Per-Strategy Monte Carlo", "=" * 72, f"Status: {status}", f"Reason: {reason}",
             "No orders were sent. This is diagnostics only.", ""]
        ),
        encoding="utf-8",
    )
    return StrategyMonteCarloResult(status, reason, paths["table"], paths["summary"], paths["latest"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Edge lab config path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Report output directory.")
    parser.add_argument("--n-sims", type=int, default=1000, help="Monte Carlo simulations per strategy.")
    parser.add_argument("--n-trades", type=int, default=100, help="Trades per simulated sequence.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_strategy_montecarlo(
        config_path=args.config, output_dir=args.output_dir, n_sims=args.n_sims, n_trades=args.n_trades
    )
    print("=" * 72)
    print("XAU Auto Trader - Per-Strategy Monte Carlo")
    print("=" * 72)
    print(f"Status: {result.status}")
    print(f"Table: {result.table_path}")
    print(f"Summary: {result.summary_path}")
    print(f"Latest: {result.latest_path}")
    print("No orders were sent. This is diagnostics only.")


if __name__ == "__main__":
    main()
