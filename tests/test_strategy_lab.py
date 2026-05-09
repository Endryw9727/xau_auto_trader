import pandas as pd

from src.lab.strategy_lab import (
    StrategyVariant,
    default_strategy_variants,
    export_strategy_lab_results,
    run_strategy_lab,
)


def make_lab_data(rows: int = 320) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=rows, freq="15min")
    base = pd.Series(range(rows), index=index).astype(float)

    return pd.DataFrame(
        {
            "Open": 2300 + base * 0.05,
            "High": 2301 + base * 0.05,
            "Low": 2299 + base * 0.05,
            "Close": 2300.5 + base * 0.05,
            "Volume": 1000,
        },
        index=index,
    )


def test_default_strategy_variants_exist():
    variants = default_strategy_variants()

    assert len(variants) > 0
    assert all(variant.allowed_sessions for variant in variants)


def test_run_strategy_lab_returns_dataframe():
    data = make_lab_data()
    variants = [
        StrategyVariant(
            name="test_variant",
            allowed_sessions=["Asia", "New York", "Off Session"],
            risk_per_trade=0.005,
            min_risk_reward=2.0,
        )
    ]

    results = run_strategy_lab(data, variants=variants)

    assert len(results) == 1
    assert results.iloc[0]["name"] == "test_variant"
    assert "profit_factor" in results.columns
    assert "max_drawdown" in results.columns


def test_export_strategy_lab_results(tmp_path):
    data = pd.DataFrame(
        [
            {
                "name": "test",
                "profit_factor": 1.2,
                "net_profit": 100,
            }
        ]
    )

    output = export_strategy_lab_results(
        data,
        output_path=tmp_path / "results.csv",
    )

    assert output.exists()
