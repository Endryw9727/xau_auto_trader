from pathlib import Path

import numpy as np
import pandas as pd

from scripts import run_overnight_anomaly as runner
from src.analysis import overnight_anomaly as anomaly


def _build_data(*, overnight_drift: float, intraday_drift: float, noise: float, days: int = 300, seed: int = 5) -> pd.DataFrame:
    """Synthetic hourly candles with a controllable overnight gap and intraday drift."""
    rng = np.random.default_rng(seed)
    rows = []
    price = 100.0
    start = pd.Timestamp("2025-01-01")
    for day in range(days):
        base = start + pd.Timedelta(days=day)
        # Overnight gap injected on the first candle of the day.
        gap = overnight_drift + rng.normal(0, noise)
        price = price * (1 + gap / 100.0)
        for hour in range(24):
            ts = base + pd.Timedelta(hours=hour)
            step = (intraday_drift / 24.0) + rng.normal(0, noise)
            open_p = price
            close_p = price * (1 + step / 100.0)
            high = max(open_p, close_p) * 1.0005
            low = min(open_p, close_p) * 0.9995
            rows.append({"Date": ts, "Open": open_p, "High": high, "Low": low, "Close": close_p, "Volume": 100})
            price = close_p
    return pd.DataFrame(rows)


def test_compute_overnight_intraday_returns():
    daily = anomaly.compute_overnight_intraday_returns(_build_data(overnight_drift=0.0, intraday_drift=0.0, noise=0.02, days=5))
    assert list(daily.columns) == list(anomaly.DAILY_COLUMNS)
    assert len(daily) == 5
    # First overnight return is NaN (no previous day).
    assert pd.isna(daily["overnight_return_pct"].iloc[0])


def test_detects_overnight_long_edge():
    data = _build_data(overnight_drift=0.05, intraday_drift=0.0, noise=0.03, days=320)
    edges = anomaly.evaluate_overnight_anomaly(data, cost_per_trade=0.0, min_trades=40)

    overnight = edges[edges["leg"] == "OVERNIGHT_LONG"].iloc[0]
    assert bool(overnight["robust_edge"]) is True
    assert overnight["mean_net_pct"] > 0


def test_detects_intraday_short_edge():
    data = _build_data(overnight_drift=0.0, intraday_drift=-0.05, noise=0.03, days=320)
    edges = anomaly.evaluate_overnight_anomaly(data, cost_per_trade=0.0, min_trades=40)

    intraday = edges[edges["leg"] == "INTRADAY_SHORT"].iloc[0]
    assert bool(intraday["robust_edge"]) is True
    assert intraday["mean_net_pct"] > 0


def test_no_edge_when_flat():
    data = _build_data(overnight_drift=0.0, intraday_drift=0.0, noise=0.05, days=320)
    edges = anomaly.evaluate_overnight_anomaly(data, cost_per_trade=0.0, min_trades=40)
    assert not edges["robust_edge"].any()


def test_empty_inputs():
    assert anomaly.compute_overnight_intraday_returns(pd.DataFrame()).empty
    assert anomaly.evaluate_overnight_anomaly(pd.DataFrame()).empty


def test_runner_applies_correction(tmp_path, monkeypatch):
    csv = tmp_path / "x.csv"
    _build_data(overnight_drift=0.05, intraday_drift=0.0, noise=0.03, days=320).to_csv(csv, index=False)
    config = {"min_trades": 40, "oos_fraction": 0.3, "t_stat_threshold": 1.5,
              "instruments": [{"symbol": "X", "csv": str(csv), "cost_per_trade": 0.0}]}
    config_path = tmp_path / "edge_lab.yaml"
    import yaml

    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(runner, "load_csv_data", lambda p: pd.read_csv(p, parse_dates=["Date"]).set_index("Date"))

    result = runner.run_overnight_anomaly(config_path=config_path, output_dir=tmp_path / "out")
    assert result.status == "OK"
    audit = pd.read_csv(result.audit_path)
    assert "mtc_robust" in audit.columns
    assert "pre-registered" in result.latest_path.read_text(encoding="utf-8").lower()


def test_runner_no_orders():
    source = Path("scripts/run_overnight_anomaly.py").read_text(encoding="utf-8")
    assert "order_send" not in source
    assert "v51_demo_executor" not in source
