from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import run_session_edge_lab as runner
from src.analysis import session_edge_lab as lab


def _build_data(*, asia_drift: float, noise: float, days: int = 200, seed: int = 7) -> pd.DataFrame:
    """Synthetic 1h candles. Asia session gets a consistent positive drift."""
    rng = np.random.default_rng(seed)
    rows = []
    price = 100.0
    start = pd.Timestamp("2025-01-01")
    for day in range(days):
        base = start + pd.Timedelta(days=day)
        for hour in range(24):
            ts = base + pd.Timedelta(hours=hour)
            drift = asia_drift if 0 <= hour < 10 else 0.0
            step = drift + rng.normal(0, noise)
            open_p = price
            close_p = price * (1 + step / 100.0)
            high = max(open_p, close_p) * 1.0005
            low = min(open_p, close_p) * 0.9995
            rows.append({"Date": ts, "Open": open_p, "High": high, "Low": low, "Close": close_p, "Volume": 100})
            price = close_p
    return pd.DataFrame(rows)


def test_compute_session_trades_one_per_session_day():
    data = _build_data(asia_drift=0.0, noise=0.05, days=3)
    trades = lab.compute_session_trades(data)
    # 3 sessions (ASIA/LONDON/NEW YORK) x 3 days = 9 trades.
    assert len(trades) == 9
    assert set(trades["session"]) == {"ASIA", "LONDON", "NEW YORK"}


def test_edge_detected_on_injected_asia_drift():
    data = _build_data(asia_drift=0.05, noise=0.05, days=240)
    edges = lab.evaluate_session_edges(data, cost_per_trade=0.0, min_trades=40)

    asia_long = edges[(edges["session"] == "ASIA") & (edges["direction"] == "LONG")].iloc[0]
    assert asia_long["robust_edge"] is True or bool(asia_long["robust_edge"])
    assert asia_long["mean_net_pct"] > 0
    assert asia_long["oos_t_stat"] > 1.5

    verdict = lab.symbol_edge_verdict("SYNTH", edges)
    assert verdict.verdict == "KEEP"
    assert verdict.best_session == "ASIA"
    assert verdict.best_direction == "LONG"


def test_no_edge_on_flat_instrument():
    data = _build_data(asia_drift=0.0, noise=0.05, days=240)
    edges = lab.evaluate_session_edges(data, cost_per_trade=0.0, min_trades=40)

    assert not edges["robust_edge"].any()
    verdict = lab.symbol_edge_verdict("FLAT", edges)
    assert verdict.verdict == "EXCLUDE"


def test_cost_destroys_marginal_edge():
    data = _build_data(asia_drift=0.02, noise=0.05, days=240)
    no_cost = lab.evaluate_session_edges(data, cost_per_trade=0.0, min_trades=40)
    high_cost = lab.evaluate_session_edges(data, cost_per_trade=5.0, min_trades=40)  # 5% cost

    assert high_cost["robust_edge"].sum() <= no_cost["robust_edge"].sum()
    assert lab.symbol_edge_verdict("X", high_cost).verdict == "EXCLUDE"


def test_evaluate_validates_oos_fraction():
    data = _build_data(asia_drift=0.0, noise=0.05, days=10)
    with pytest.raises(ValueError):
        lab.evaluate_session_edges(data, oos_fraction=0.0)
    with pytest.raises(ValueError):
        lab.evaluate_session_edges(data, oos_fraction=1.0)


def test_empty_inputs():
    assert lab.compute_session_trades(pd.DataFrame()).empty
    assert lab.evaluate_session_edges(pd.DataFrame()).empty
    assert lab.symbol_edge_verdict("X", pd.DataFrame()).verdict == "EXCLUDE"


def test_runner_keep_and_exclude(tmp_path, monkeypatch):
    edge_csv = tmp_path / "edge.csv"
    flat_csv = tmp_path / "flat.csv"
    _build_data(asia_drift=0.05, noise=0.05, days=240).to_csv(edge_csv, index=False)
    _build_data(asia_drift=0.0, noise=0.05, days=240).to_csv(flat_csv, index=False)

    config = {
        "min_trades": 40,
        "oos_fraction": 0.3,
        "t_stat_threshold": 1.5,
        "instruments": [
            {"symbol": "EDGE", "csv": str(edge_csv), "cost_per_trade": 0.0},
            {"symbol": "FLAT", "csv": str(flat_csv), "cost_per_trade": 0.0},
            {"symbol": "GONE", "csv": str(tmp_path / "missing.csv"), "cost_per_trade": 0.0},
        ],
    }
    config_path = tmp_path / "edge_lab.yaml"
    import yaml

    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(runner, "load_csv_data", lambda p: pd.read_csv(p, parse_dates=["Date"]).set_index("Date"))

    result = runner.run_session_edge_lab(config_path=config_path, output_dir=tmp_path / "out")

    assert result.status == "OK"
    verdicts = pd.read_csv(result.verdict_path).set_index("symbol")
    assert verdicts.loc["EDGE", "verdict"] == "KEEP"
    assert verdicts.loc["FLAT", "verdict"] == "EXCLUDE"
    assert verdicts.loc["GONE", "status"] == "NO_DATA"
    text = result.latest_path.read_text(encoding="utf-8")
    assert "No orders were sent" in text


def test_runner_does_not_execute_orders():
    source = Path("scripts/run_session_edge_lab.py").read_text(encoding="utf-8")
    assert "order_send" not in source
    assert "v51_demo_executor" not in source
    assert "run_v51_demo_execution_once" not in source
