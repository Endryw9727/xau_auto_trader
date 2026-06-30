from pathlib import Path

import numpy as np
import pandas as pd

from scripts import run_ny_conditional_edge as runner
from src.analysis import ny_conditional_edge as ny


def _build_data(*, continuation: bool, noise: float, days: int = 260, seed: int = 11) -> pd.DataFrame:
    """Synthetic 1h candles where NY continues (or reverses) the pre-NY move."""
    rng = np.random.default_rng(seed)
    rows = []
    price = 100.0
    start = pd.Timestamp("2025-01-01")
    for day in range(days):
        base = start + pd.Timedelta(days=day)
        pre_dir = 1.0 if rng.random() < 0.5 else -1.0
        for hour in range(24):
            ts = base + pd.Timedelta(hours=hour)
            if 0 <= hour < 16:  # pre-NY (Asia + London)
                drift = pre_dir * 0.03
            elif 18 <= hour < 23:  # New York
                ny_dir = pre_dir if continuation else -pre_dir
                drift = ny_dir * 0.05
            else:
                drift = 0.0
            step = drift + rng.normal(0, noise)
            open_p = price
            close_p = price * (1 + step / 100.0)
            high = max(open_p, close_p) * 1.0005
            low = min(open_p, close_p) * 0.9995
            rows.append({"Date": ts, "Open": open_p, "High": high, "Low": low, "Close": close_p, "Volume": 100})
            price = close_p
    return pd.DataFrame(rows)


def test_build_ny_daily_frame_no_lookahead_columns():
    daily = ny.build_ny_daily_frame(_build_data(continuation=True, noise=0.02, days=5))
    assert list(daily.columns) == list(ny.NY_DAILY_COLUMNS)
    assert len(daily) == 5


def test_detects_continuation_edge():
    data = _build_data(continuation=True, noise=0.03, days=300)
    edges = ny.evaluate_ny_conditional_edges(data, cost_per_trade=0.0, min_trades=30)

    robust = edges[edges["robust_edge"]]
    assert not robust.empty
    # Continuation: PRE_UP -> LONG and/or PRE_DOWN -> SHORT should be robust.
    assert (robust["hypothesis"] == "CONTINUATION").any()


def test_detects_reversal_edge():
    data = _build_data(continuation=False, noise=0.03, days=300)
    edges = ny.evaluate_ny_conditional_edges(data, cost_per_trade=0.0, min_trades=30)

    robust = edges[edges["robust_edge"]]
    assert not robust.empty
    assert (robust["hypothesis"] == "REVERSAL").any()


def test_cost_removes_edge():
    data = _build_data(continuation=True, noise=0.03, days=300)
    high_cost = ny.evaluate_ny_conditional_edges(data, cost_per_trade=10.0, min_trades=30)
    assert not high_cost["robust_edge"].any()


def test_empty_inputs():
    assert ny.build_ny_daily_frame(pd.DataFrame()).empty
    assert ny.evaluate_ny_conditional_edges(pd.DataFrame()).empty


def test_runner_keep_and_exclude(tmp_path, monkeypatch):
    cont_csv = tmp_path / "cont.csv"
    flat_csv = tmp_path / "flat.csv"
    _build_data(continuation=True, noise=0.03, days=300).to_csv(cont_csv, index=False)
    _build_data(continuation=True, noise=0.5, days=300, seed=99).to_csv(flat_csv, index=False)

    config = {
        "min_trades": 30, "oos_fraction": 0.3, "t_stat_threshold": 1.5,
        "instruments": [
            {"symbol": "CONT", "csv": str(cont_csv), "cost_per_trade": 0.0},
            {"symbol": "FLAT", "csv": str(flat_csv), "cost_per_trade": 0.0},
            {"symbol": "GONE", "csv": str(tmp_path / "missing.csv"), "cost_per_trade": 0.0},
        ],
    }
    config_path = tmp_path / "edge_lab.yaml"
    import yaml

    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(runner, "load_csv_data", lambda p: pd.read_csv(p, parse_dates=["Date"]).set_index("Date"))

    result = runner.run_ny_conditional_edge(config_path=config_path, output_dir=tmp_path / "out")

    assert result.status == "OK"
    verdicts = pd.read_csv(result.verdict_path).set_index("symbol")
    assert verdicts.loc["CONT", "verdict"] == "KEEP"
    assert verdicts.loc["GONE", "status"] == "NO_DATA"
    assert "No orders were sent" in result.latest_path.read_text(encoding="utf-8")


def test_runner_does_not_execute_orders():
    source = Path("scripts/run_ny_conditional_edge.py").read_text(encoding="utf-8")
    assert "order_send" not in source
    assert "v51_demo_executor" not in source
    assert "run_v51_demo_execution_once" not in source
