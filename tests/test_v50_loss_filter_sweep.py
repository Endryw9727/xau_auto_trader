from pathlib import Path

import pandas as pd

from scripts import analyze_v50_loss_filter_selection as selection_script
from scripts import run_v50_loss_filter_sweep as sweep_script
from src.strategy_lab.strategy_v50_candidates import FINAL_BALANCED_STRATEGY_NAME
from src.strategy_lab.v50_loss_filter_sweep import (
    LOSS_FILTER_SWEEP_COLUMNS,
    LOSS_FILTER_VARIANT_NAMES,
    build_loss_filter_variants,
    run_v50_loss_filter_sweep,
)


def make_trades(repeats: int = 6) -> pd.DataFrame:
    rows = []
    base_pnl = [10.0, -5.0, -6.0, 12.0, -4.0, -3.0, 14.0, -5.0, 11.0, 8.0]
    for repeat in range(repeats):
        for index, value in enumerate(base_pnl):
            rows.append(
                {
                    "strategy_name": FINAL_BALANCED_STRATEGY_NAME,
                    "entry_time": pd.Timestamp("2025-01-01 09:00:00") + pd.Timedelta(hours=6 * (repeat * len(base_pnl) + index)),
                    "side": "BUY" if index % 2 == 0 else "SELL",
                    "side_label": "LONG" if index % 2 == 0 else "SHORT",
                    "session": ["LONDON", "NEW YORK", "ASIA", "LONDON", "LONDON"][index % 5],
                    "pnl": value,
                    "profit_loss": value,
                    "score_long": 82 if index % 2 == 0 else 30,
                    "score_short": 76 if index % 2 else 25,
                    "bars_in_trade": [4, 8, 9, 3, 1][index % 5],
                }
            )
    return pd.DataFrame(rows)


def make_market_data() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=30, freq="D")
    return pd.DataFrame(
        {
            "Open": [100.0] * len(dates),
            "High": [105.0] * len(dates),
            "Low": [99.0] * len(dates),
            "Close": [103.0] * len(dates),
            "Volume": [1.0] * len(dates),
        },
        index=dates,
    )


def test_loss_filter_variants_include_required_names():
    names = [variant.variant_name for variant in build_loss_filter_variants(make_trades())]

    assert names == list(LOSS_FILTER_VARIANT_NAMES)


def test_loss_filter_sweep_generates_expected_columns(tmp_path):
    output_path = tmp_path / "v50_loss_filter_sweep.csv"
    report = run_v50_loss_filter_sweep(
        trades=make_trades(),
        market_data=make_market_data(),
        output_path=output_path,
    )
    exported = pd.read_csv(output_path)

    assert output_path.exists()
    assert set(exported["variant_name"]) == set(LOSS_FILTER_VARIANT_NAMES)
    assert set(LOSS_FILTER_SWEEP_COLUMNS).issubset(report.columns)


def test_loss_filter_sweep_script_runs(monkeypatch, tmp_path, capsys):
    output_path = tmp_path / "v50_loss_filter_sweep.csv"
    raw_path = tmp_path / "xauusd.csv"
    raw_path.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(sweep_script, "DEFAULT_LOSS_FILTER_SWEEP_PATH", output_path)
    monkeypatch.setattr(sweep_script, "RAW_DATA_PATH", raw_path)
    monkeypatch.setattr(sweep_script, "load_loss_trade_report", lambda: make_trades())
    monkeypatch.setattr(sweep_script, "load_csv_data", lambda _path: make_market_data())

    sweep_script.main()
    output = capsys.readouterr().out

    assert output_path.exists()
    assert "V50 Loss Filter Sweep" in output
    assert "No variant was promoted automatically." in output


def test_loss_filter_selection_helpers():
    report = pd.DataFrame(
        [
            {
                "variant_name": "loss_filter_base",
                "total_trades": 800,
                "average_trades_per_day": 0.8,
                "active_day_ratio": 0.7,
                "profit_factor": 1.20,
                "net_profit": 100.0,
                "max_drawdown": 100.0,
                "profit_drawdown_ratio": 1.0,
                "max_consecutive_losses": 11,
                "anti_overfit_pass": True,
            },
            {
                "variant_name": "block_worst_hour",
                "total_trades": 760,
                "average_trades_per_day": 0.76,
                "active_day_ratio": 0.68,
                "profit_factor": 1.27,
                "net_profit": 110.0,
                "max_drawdown": 75.0,
                "profit_drawdown_ratio": 1.46,
                "max_consecutive_losses": 8,
                "anti_overfit_pass": True,
            },
        ]
    )
    ranking = selection_script.prepare_loss_filter_ranking(report)
    base = selection_script.base_row(ranking)

    assert selection_script.select_best_profit_factor(ranking)["variant_name"] == "block_worst_hour"
    assert selection_script.exists_pf_with_frequency(ranking, 1.25, 0.75)
    assert selection_script.exists_pf_with_dd_reduction(ranking, base, 1.20, 0.20)


def test_v50_loss_filter_sources_are_research_only():
    checked_files = [
        Path("src/strategy_lab/v50_loss_filter_sweep.py"),
        Path("scripts/run_v50_loss_filter_sweep.py"),
        Path("scripts/analyze_v50_loss_filter_selection.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
