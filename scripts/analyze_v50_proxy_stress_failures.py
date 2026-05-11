"""
Analyze why v50_proxy_balanced_candidate fails selected robustness checks.

Reads local research reports only and exports a stress-failure comparison CSV.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy_lab.v50_monte_carlo import DEFAULT_V50_MONTE_CARLO_PATH
from src.strategy_lab.v50_proxy_hardening import (
    DEFAULT_PROXY_STRESS_FAILURE_ANALYSIS_PATH,
    build_proxy_stress_failure_analysis,
    export_proxy_stress_failure_analysis,
)
from src.strategy_lab.v50_stress_test import DEFAULT_V50_STRESS_TEST_PATH


STRATEGY_COMPARISON_PATH = Path("reports/strategy_lab/strategy_comparison.csv")
PROXY_NAME = "v50_proxy_balanced_candidate"


def main() -> None:
    """Print and export proxy stress-failure diagnostics."""
    print("=" * 72)
    print("XAU Auto Trader - V50 Proxy Stress Failures")
    print("=" * 72)

    stress = _load_required_csv(DEFAULT_V50_STRESS_TEST_PATH)
    monte_carlo = _load_required_csv(DEFAULT_V50_MONTE_CARLO_PATH)
    comparison = _load_required_csv(STRATEGY_COMPARISON_PATH)
    if stress is None or monte_carlo is None or comparison is None:
        print("Run first: Strategy Lab, stress test and Monte Carlo reports.")
        return

    analysis = build_proxy_stress_failure_analysis(stress, monte_carlo, comparison)
    output_path = export_proxy_stress_failure_analysis(analysis, DEFAULT_PROXY_STRESS_FAILURE_ANALYSIS_PATH)

    proxy_rows = analysis[analysis["strategy_name"] == PROXY_NAME]
    print("")
    print("Proxy scenarios with PF below 1.20:")
    _print_table(proxy_rows[proxy_rows["pf_below_1_20"]].sort_values("profit_factor"))
    print("")
    print("Worst net-profit degradation:")
    _print_table(proxy_rows.sort_values("net_profit_delta_vs_base").head(5))
    print("")
    print("Worst drawdown degradation:")
    _print_table(proxy_rows.sort_values("max_drawdown_delta_vs_base", ascending=False).head(5))
    print("")
    print("Scenario-by-scenario comparison:")
    _print_table(analysis.sort_values(["scenario", "strategy_name"]))
    print("")
    print(f"Stress failure analysis exported: {output_path}")
    print("No candidate was promoted automatically.")


def _print_table(table: pd.DataFrame) -> None:
    if table.empty:
        print("(no data)")
        return
    print(table.to_string(index=False))


def _load_required_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        print(f"Missing report: {path}")
        return None
    print(f"Loaded report: {path}")
    return pd.read_csv(path)


if __name__ == "__main__":
    main()
