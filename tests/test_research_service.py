import json
import math
import time
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


def test_overfitting_shape(tmp_path):
    out = service.overfitting(config_path=_config(tmp_path))
    assert out["live_armed"] is False
    assert out["status"] in {"OK", "INSUFFICIENT_DATA"}
    assert "deflated_sharpe_ratio" in out
    assert "probability_of_backtest_overfitting" in out
    assert isinstance(out["strategies"], list)
    json.dumps(out, allow_nan=False)  # strict JSON


def test_montecarlo_shape(tmp_path):
    out = service.montecarlo(config_path=_config(tmp_path))
    assert out["live_armed"] is False
    assert out["status"] in {"OK", "INSUFFICIENT_DATA"}
    assert "n_profitable" in out
    assert isinstance(out["rows"], list)
    json.dumps(out, allow_nan=False)  # strict JSON


def test_regime_conditional_shape(tmp_path):
    out = service.regime_conditional(config_path=_config(tmp_path))
    assert out["live_armed"] is False
    assert out["status"] in {"OK", "INSUFFICIENT_DATA"}
    assert "mtc_survivors" in out
    assert "deflated_sharpe_ratio" in out
    assert isinstance(out["rows"], list)
    json.dumps(out, allow_nan=False)  # strict JSON


def test_overrides_are_applied(tmp_path):
    # A very high threshold must wipe out any robust edge.
    out = service.significance_audit(config_path=_config(tmp_path), t_stat_threshold=99.0)
    assert out["walk_forward_robust"] == 0
    assert out["mtc_survivors"] == 0


def test_json_safe_replaces_non_finite():
    cleaned = service._json_safe({"a": float("nan"), "b": float("inf"), "c": 1.5, "d": [float("nan"), 2]})
    assert cleaned["a"] is None
    assert cleaned["b"] is None
    assert cleaned["c"] == 1.5
    assert cleaned["d"] == [None, 2]


def test_significance_audit_is_strict_json(tmp_path):
    # Starlette's JSONResponse uses allow_nan=False; the payload must survive it.
    out = service.significance_audit(config_path=_config(tmp_path))
    json.dumps(out, allow_nan=False)  # must not raise
    for row in out["rows"]:
        for value in row.values():
            assert not (isinstance(value, float) and not math.isfinite(value))


def test_session_scan_is_strict_json(tmp_path):
    out = service.session_scan(config_path=_config(tmp_path))
    json.dumps(out, allow_nan=False)  # must not raise


def test_read_records_has_no_nan(tmp_path):
    csv = tmp_path / "x.csv"
    pd.DataFrame({"a": [1.0, None], "b": ["x", "y"]}).to_csv(csv, index=False)
    records = service._read_records(csv)
    assert records[1]["a"] is None  # NaN became None, not float('nan')
    json.dumps(records, allow_nan=False)


def test_cache_bypassed_for_custom_config(tmp_path):
    custom = tmp_path / "edge_lab.yaml"
    assert service._cache_key("x", custom, {}) is None
    service._cache_put("x", custom, {}, {"a": 1})
    assert service._cache_get("x", custom, {}) is None  # never cached for custom configs


def test_cache_roundtrip_for_default_config():
    service._cache_put("unit_test_marker", service.DEFAULT_EDGE_CONFIG, {}, {"ok": 1})
    assert service._cache_get("unit_test_marker", service.DEFAULT_EDGE_CONFIG, {}) == {"ok": 1}


def test_cached_call_computes_once_when_warm():
    # Cold call computes; a second call with unchanged data returns the cached
    # result WITHOUT recomputing.
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"n": calls["n"]}

    r1 = service._cached_call("t_swr_warm", service.DEFAULT_EDGE_CONFIG, {}, compute)
    r2 = service._cached_call("t_swr_warm", service.DEFAULT_EDGE_CONFIG, {}, compute)
    assert r1 == r2 == {"n": 1}
    assert calls["n"] == 1


def test_cached_call_serves_stale_then_refreshes_in_background():
    # A stale entry (bogus signature) must be served immediately, with a
    # background recompute updating the cache for the next call.
    key = service._cache_key("t_swr_stale", service.DEFAULT_EDGE_CONFIG, {})
    with service._cache_lock:
        service._cache[key] = (time.time(), (("bogus.csv", 1),), {"v": "old"})
    seen = {"n": 0}

    def compute():
        seen["n"] += 1
        return {"v": "new"}

    out = service._cached_call("t_swr_stale", service.DEFAULT_EDGE_CONFIG, {}, compute)
    assert out == {"v": "old"}  # stale result served instantly, no blocking compute

    fresh = None
    for _ in range(100):
        with service._cache_lock:
            fresh = service._cache[key][2]
        if fresh == {"v": "new"}:
            break
        time.sleep(0.05)
    assert fresh == {"v": "new"}
    assert seen["n"] == 1


def test_cached_call_bypasses_cache_for_custom_config(tmp_path):
    custom = tmp_path / "edge_lab.yaml"
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"n": calls["n"]}

    service._cached_call("t_swr_custom", custom, {}, compute)
    service._cached_call("t_swr_custom", custom, {}, compute)
    assert calls["n"] == 2  # custom configs are never cached


def test_warm_cache_is_callable():
    # Best-effort warmer must never raise even if data is missing.
    service.warm_cache()


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
