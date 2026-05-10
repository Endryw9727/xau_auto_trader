from pathlib import Path

import pandas as pd

from src.strategy_lab.strategy_diagnostics import (
    DEFAULT_DIAGNOSTIC_STRATEGIES,
    DIAGNOSTIC_COLUMNS,
    build_strategy_diagnostics,
    export_strategy_diagnostics,
)


def make_walk_forward_report() -> pd.DataFrame:
    rows = []
    strategy_periods = {
        "v50_pine_technical_strategy": [
            (30, 1.20, 50.0, 20.0),
            (25, 1.10, 20.0, 12.0),
            (18, 0.90, -10.0, 18.0),
            (27, 1.30, 35.0, 14.0),
        ],
        "v50_low_risk_london_strategy": [
            (22, 1.25, 45.0, 13.0),
            (18, 1.18, 28.0, 10.0),
            (14, 0.92, -8.0, 11.0),
            (20, 1.22, 32.0, 12.0),
        ],
        "v50_balanced_no_asia_london_strategy": [
            (26, 1.16, 42.0, 18.0),
            (21, 1.08, 18.0, 15.0),
            (19, 0.88, -14.0, 19.0),
            (24, 1.24, 38.0, 16.0),
        ],
        "v50_growth_long_all_short_london_strategy": [
            (35, 1.12, 58.0, 24.0),
            (32, 1.06, 22.0, 20.0),
            (28, 0.95, -16.0, 22.0),
            (34, 1.19, 48.0, 21.0),
        ],
        "v50_pine_mtf_strategy": [
            (0, 0.00, 0.0, 0.0),
            (42, 1.50, 90.0, 30.0),
            (0, 0.00, 0.0, 0.0),
            (38, 0.80, -25.0, 22.0),
        ],
        "mtf_relaxed_offasia_strategy": [
            (80, 1.05, 25.0, 15.0),
            (75, 1.12, 35.0, 17.0),
            (70, 0.95, -18.0, 25.0),
            (85, 1.08, 40.0, 16.0),
        ],
        "mtf_feature_filtered_strategy": [
            (20, 1.15, 18.0, 9.0),
            (0, 0.00, 0.0, 0.0),
            (18, 1.25, 28.0, 11.0),
            (15, 0.85, -12.0, 10.0),
        ],
        "unrelated_strategy": [
            (100, 2.00, 200.0, 50.0),
        ],
    }

    for strategy_name, periods in strategy_periods.items():
        for index, (trades, profit_factor, net_profit, drawdown) in enumerate(periods):
            rows.append(
                {
                    "strategy_name": strategy_name,
                    "period_start": f"2025-0{index + 1}-01",
                    "period_end": f"2025-0{index + 1}-28",
                    "total_trades": trades,
                    "wins": 0,
                    "losses": 0,
                    "win_rate": 0.0,
                    "profit_factor": profit_factor,
                    "net_profit": net_profit,
                    "max_drawdown": drawdown,
                    "expectancy": 0.0,
                    "average_trade": 0.0,
                    "max_consecutive_losses": 0,
                }
            )

    return pd.DataFrame(rows)


def make_strategy_comparison() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "strategy_name": strategy_name,
                "total_trades": 1000 + index,
                "profit_factor": 1.0 + index / 100,
                "net_profit": 100.0 + index,
                "max_drawdown": 50.0 + index,
            }
            for index, strategy_name in enumerate(DEFAULT_DIAGNOSTIC_STRATEGIES)
        ]
    )


def test_strategy_diagnostics_contains_required_columns_and_target_strategies():
    diagnostics = build_strategy_diagnostics(
        make_walk_forward_report(),
        make_strategy_comparison(),
    )

    assert list(diagnostics.columns) == DIAGNOSTIC_COLUMNS
    assert set(diagnostics["strategy_name"]) == set(DEFAULT_DIAGNOSTIC_STRATEGIES)
    assert "unrelated_strategy" not in set(diagnostics["strategy_name"])


def test_strategy_diagnostics_counts_active_and_no_trade_periods():
    diagnostics = build_strategy_diagnostics(make_walk_forward_report())
    mtf = diagnostics.set_index("strategy_name").loc["v50_pine_mtf_strategy"]

    assert mtf["total_periods"] == 4
    assert mtf["active_periods"] == 2
    assert mtf["no_trade_periods"] == 2
    assert mtf["positive_periods"] == 1
    assert mtf["negative_periods"] == 1
    assert mtf["total_trades"] == 80
    assert mtf["avg_trades_per_active_period"] == 40.0


def test_strategy_diagnostics_profit_factor_uses_active_periods_only():
    diagnostics = build_strategy_diagnostics(make_walk_forward_report())
    mtf = diagnostics.set_index("strategy_name").loc["v50_pine_mtf_strategy"]

    assert mtf["average_profit_factor"] == 1.15
    assert mtf["median_profit_factor"] == 1.15


def test_strategy_diagnostics_exports_csv(tmp_path):
    diagnostics = build_strategy_diagnostics(make_walk_forward_report())
    output_path = export_strategy_diagnostics(
        diagnostics,
        tmp_path / "strategy_diagnostics.csv",
    )
    exported = pd.read_csv(output_path)

    assert output_path.exists()
    assert list(exported.columns) == DIAGNOSTIC_COLUMNS


def test_strategy_diagnostics_research_only_without_broker_or_api_references():
    checked_files = [
        Path("scripts/analyze_strategy_diagnostics.py"),
        Path("src/strategy_lab/strategy_diagnostics.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
