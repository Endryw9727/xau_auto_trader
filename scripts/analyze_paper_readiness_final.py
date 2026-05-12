"""
Analyze final paper readiness for the controlled V50 candidates.

The output is a research recommendation for paper mode only. It never promotes
any strategy to real execution.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.paper.paper_engine import DEFAULT_PAPER_SUMMARY_PATH, load_paper_trading_config


MAIN_COLUMNS = [
    "strategy_name",
    "ending_equity",
    "net_profit",
    "profit_factor_net",
    "max_dd_pct",
    "max_dd_eur",
    "total_trades",
    "trades_per_day",
    "win_rate",
    "expectancy",
    "max_consecutive_losses",
    "worst_day",
    "worst_week",
    "worst_month",
    "months_positive",
    "months_negative",
    "no_trade_days",
    "max_no_trade_days",
    "time_to_1500_if_reached",
    "time_to_2000_if_reached",
    "drawdown_over_8_pct",
    "drawdown_over_10_pct",
    "drawdown_over_12_pct",
]


def main() -> None:
    """Print final paper readiness diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - Final Paper Readiness")
    print("=" * 72)

    config = load_paper_trading_config()
    summary = load_summary(DEFAULT_PAPER_SUMMARY_PATH)
    if summary is None:
        print("Run first: python scripts/run_paper_simulation.py")
        return

    prepared = prepare_summary(summary)
    main_row = row_for_strategy(prepared, config.strategy_name)
    backup_row = row_for_strategy(prepared, config.backup_strategy)

    print("")
    print("Candidate comparison:")
    print(prepared[[column for column in MAIN_COLUMNS if column in prepared.columns]].to_string(index=False))

    print("")
    print("Recommended paper candidate:")
    print(format_strategy_line(main_row))

    print("")
    print("Prudent backup candidate:")
    print(format_strategy_line(backup_row))

    print("")
    print("Paper readiness:")
    print(build_paper_readiness_text(main_row, backup_row, config))

    print("")
    print("Not ready for live:")
    print("This remains paper/research only. Real execution requires explicit future approval and separate controls.")

    print("")
    print("Immediate paper-stop conditions:")
    print(build_stop_conditions(config))

    print("")
    print("Minimum conditions before any later demo/micro-live discussion:")
    print(build_transition_conditions())

    print("")
    print("No strategy was promoted automatically.")


def load_summary(path: Path = DEFAULT_PAPER_SUMMARY_PATH) -> pd.DataFrame | None:
    """Load paper summary if it exists."""
    if not path.exists():
        print(f"Missing report: {path}")
        return None
    print(f"Loaded report: {path}")
    return pd.read_csv(path)


def prepare_summary(summary: pd.DataFrame) -> pd.DataFrame:
    """Normalize numeric columns used by selection text."""
    result = summary.copy()
    numeric_columns = [
        "ending_equity",
        "net_profit",
        "profit_factor_net",
        "max_dd_pct",
        "max_dd_eur",
        "total_trades",
        "trades_per_day",
        "win_rate",
        "expectancy",
        "max_consecutive_losses",
        "worst_day",
        "worst_week",
        "worst_month",
        "months_positive",
        "months_negative",
        "no_trade_days",
        "max_no_trade_days",
    ]
    for column in numeric_columns:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def row_for_strategy(summary: pd.DataFrame, strategy_name: str) -> pd.Series:
    """Return one strategy row or raise a clear error."""
    match = summary[summary["strategy_name"] == strategy_name]
    if match.empty:
        raise ValueError(f"Missing paper summary row for {strategy_name}")
    return match.iloc[0]


def is_ready_for_paper(row: pd.Series) -> bool:
    """Return True when the main candidate passes paper-readiness gates."""
    return bool(
        float(row.get("profit_factor_net", 0.0)) >= 1.25
        and float(row.get("max_dd_pct", 100.0)) <= 12.0
        and int(row.get("total_trades", 0)) >= 650
        and float(row.get("net_profit", 0.0)) > 0
        and int(row.get("max_consecutive_losses", 99)) <= 10
    )


def build_paper_readiness_text(main_row: pd.Series, backup_row: pd.Series, config) -> str:
    """Build concise readiness recommendation text."""
    if is_ready_for_paper(main_row):
        return (
            f"Ready for controlled paper study with {config.strategy_name}. "
            f"Use {config.backup_strategy} as the prudent reference because it has lower drawdown "
            "but lower frequency. Keep paper mode only."
        )
    if is_ready_for_paper(backup_row):
        return (
            f"Main candidate needs more caution; use {config.backup_strategy} as the conservative "
            "paper reference. Keep paper mode only."
        )
    return "Not ready for controlled paper. Continue research before any forward simulation."


def build_stop_conditions(config) -> str:
    """Return operational stop thresholds from config."""
    return (
        f"Pause immediately if daily loss reaches {config.max_daily_loss_pct:.1f}%, "
        f"daily consecutive losses reach {config.max_consecutive_losses_day}, "
        f"total loss streak reaches {config.max_consecutive_losses_total_warning}, "
        f"drawdown reaches {config.max_drawdown_stop_pct:.1f}%, "
        "or fills/costs materially differ from the Axi paper assumptions."
    )


def build_transition_conditions() -> str:
    """Return minimum evidence for any future non-paper discussion."""
    return (
        "At least 3 months of paper results, at least 100 forward paper trades, "
        "net PF >= 1.20 after real recorded costs, max drawdown below 8-10%, "
        "no breach of paper-stop rules, and explicit user approval in a separate future task."
    )


def format_strategy_line(row: pd.Series) -> str:
    """Format one strategy row for terminal output."""
    return (
        f"{row['strategy_name']}: PF {float(row['profit_factor_net']):.3f}, "
        f"ending equity {float(row['ending_equity']):.2f} EUR, "
        f"DD {float(row['max_dd_pct']):.2f}%, "
        f"trades {int(row['total_trades'])}, "
        f"trades/day {float(row['trades_per_day']):.3f}"
    )


if __name__ == "__main__":
    main()
