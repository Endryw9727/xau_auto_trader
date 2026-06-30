from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from src.api import research_service as service


def _synthetic_csv(path: Path, *, days: int = 200, seed: int = 3) -> Path:
    rng = np.random.default_rng(seed)
    rows = []
    price = 100.0
    start = pd.Timestamp("2025-01-01")
    for day in range(days):
        base = start + pd.Timedelta(days=day)
        for hour in range(24):
            ts = base + pd.Timedelta(hours=hour)
            step = rng.normal(0, 0.05)
            o = price
            c = price * (1 + step / 100)
            rows.append({"Date": ts, "Open": o, "High": max(o, c) * 1.001, "Low": min(o, c) * 0.999, "Close": c, "Volume": 100})
            price = c
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _config(tmp_path) -> Path:
    csv = _synthetic_csv(tmp_path / "synth.csv")
    config = {
        "min_trades": 30,
        "oos_fraction": 0.3,
        "t_stat_threshold": 1.5,
        "instruments": [{"symbol": "SYNTH", "csv": str(csv), "cost_per_trade": 0.0}],
    }
    path = tmp_path / "edge_lab.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_health_reports_disarmed():
    payload = service.health()
    assert payload["status"] == "ok"
    assert payload["live_armed"] is False


def test_list_instruments(tmp_path):
    config_path = _config(tmp_path)
    out = service.list_instruments(config_path=config_path)
    assert out["live_armed"] is False
    inst = out["instruments"][0]
    assert inst["symbol"] == "SYNTH"
    assert inst["has_data"] is True
    assert inst["rows"] > 0
    assert inst["first"] is not None


def test_list_instruments_missing_data(tmp_path):
    config = {"instruments": [{"symbol": "GONE", "csv": str(tmp_path / "nope.csv"), "cost_per_trade": 0.0}]}
    path = tmp_path / "edge_lab.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    out = service.list_instruments(config_path=path)
    assert out["instruments"][0]["has_data"] is False
    assert out["instruments"][0]["rows"] == 0


def test_session_scan_shape(tmp_path):
    out = service.session_scan(config_path=_config(tmp_path))
    assert out["status"] == "OK"
    assert out["live_armed"] is False
    assert isinstance(out["verdicts"], list) and out["verdicts"]
    assert out["verdicts"][0]["symbol"] == "SYNTH"
    assert out["verdicts"][0]["verdict"] in {"KEEP", "EXCLUDE"}


def test_significance_audit_shape(tmp_path):
    out = service.significance_audit(config_path=_config(tmp_path))
    assert out["live_armed"] is False
    assert out["family_size"] > 0
    assert isinstance(out["mtc_survivors"], int)
    assert all("mtc_robust" in row for row in out["rows"])


def test_overnight_shape(tmp_path):
    out = service.overnight(config_path=_config(tmp_path))
    assert out["live_armed"] is False
    assert isinstance(out["rows"], list)


def test_overrides_are_applied(tmp_path):
    # A very high threshold must wipe out any robust edge.
    out = service.significance_audit(config_path=_config(tmp_path), t_stat_threshold=99.0)
    assert out["walk_forward_robust"] == 0
    assert out["mtc_survivors"] == 0


def test_service_has_no_execution_imports():
    source = Path("src/api/research_service.py").read_text(encoding="utf-8")
    assert "order_send" not in source
    assert "v51_demo_executor" not in source
    assert "run_v51_demo_execution_once" not in source


@pytest.mark.skipif(not Path("data/raw/xauusd.csv").exists(), reason="needs local XAU data")
def test_bot_rejection_taxonomy_smoke():
    out = service.bot_rejection_taxonomy(candles=60)
    assert out["live_armed"] is False
    assert "rows" in out
