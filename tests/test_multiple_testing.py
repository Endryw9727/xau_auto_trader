from pathlib import Path

import pandas as pd
import pytest

from scripts import run_edge_significance_audit as audit_script
from src.analysis import multiple_testing as mt


def test_two_sided_p_from_t():
    assert mt.two_sided_p_from_t(0.0) == pytest.approx(1.0, abs=1e-6)
    # |t|=1.96 -> ~0.05 two-sided under normal approx.
    assert mt.two_sided_p_from_t(1.96) == pytest.approx(0.05, abs=0.005)
    assert mt.two_sided_p_from_t(3.0) < 0.005
    assert mt.two_sided_p_from_t(float("nan")) == 1.0


def test_bonferroni_flags():
    # m=10 -> threshold 0.005: 0.0001 significant, 0.01 not.
    pvals = [0.0001, 0.01, 0.5] + [0.9] * 7
    flags = mt.bonferroni_flags(pvals, alpha=0.05)
    assert flags[0] is True
    assert flags[1] is False
    assert flags[2] is False
    assert mt.bonferroni_flags([]) == []


def test_benjamini_hochberg_flags():
    # One very small p among noise should be discovered.
    flags = mt.benjamini_hochberg_flags([0.0001, 0.4, 0.6, 0.8], alpha=0.05)
    assert flags[0] is True
    assert flags[1:] == [False, False, False]


def test_benjamini_hochberg_is_less_strict_than_bonferroni():
    pvals = [0.001, 0.012, 0.02, 0.5, 0.6]
    bonf = mt.bonferroni_flags(pvals, alpha=0.05)
    bh = mt.benjamini_hochberg_flags(pvals, alpha=0.05)
    assert sum(bh) >= sum(bonf)


def test_audit_edges_marks_survivors():
    detail = pd.DataFrame(
        [
            {"symbol": "A", "oos_t_stat": 4.5, "robust_edge": True},   # strong, robust
            {"symbol": "B", "oos_t_stat": 1.6, "robust_edge": True},   # weak, robust -> likely fails MTC
            {"symbol": "C", "oos_t_stat": 5.0, "robust_edge": False},  # strong but not walk-forward robust
        ]
    )
    audited = mt.audit_edges(detail, t_col="oos_t_stat", alpha=0.05)

    a = audited[audited["symbol"] == "A"].iloc[0]
    assert a["mtc_robust"] is True or bool(a["mtc_robust"]) is True
    c = audited[audited["symbol"] == "C"].iloc[0]
    # Not walk-forward robust -> cannot be mtc_robust even if significant.
    assert bool(c["mtc_robust"]) is False


def test_audit_edges_empty():
    out = mt.audit_edges(pd.DataFrame())
    assert "mtc_robust" in out.columns


def test_audit_script_runs(tmp_path, monkeypatch):
    import numpy as np

    def synth(seed):
        rng = np.random.default_rng(seed)
        rows = []
        price = 100.0
        start = pd.Timestamp("2025-01-01")
        for day in range(120):
            base = start + pd.Timedelta(days=day)
            for hour in range(24):
                ts = base + pd.Timedelta(hours=hour)
                step = rng.normal(0, 0.05)
                o = price
                c = price * (1 + step / 100)
                rows.append({"Date": ts, "Open": o, "High": max(o, c) * 1.001, "Low": min(o, c) * 0.999, "Close": c, "Volume": 1})
                price = c
        return pd.DataFrame(rows)

    csv = tmp_path / "x.csv"
    synth(1).to_csv(csv, index=False)
    config = {"min_trades": 20, "oos_fraction": 0.3, "t_stat_threshold": 1.5,
              "instruments": [{"symbol": "X", "csv": str(csv), "cost_per_trade": 0.0}]}
    config_path = tmp_path / "edge_lab.yaml"
    import yaml

    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(audit_script, "load_csv_data", lambda p: pd.read_csv(p, parse_dates=["Date"]).set_index("Date"))

    result = audit_script.run_edge_significance_audit(config_path=config_path, output_dir=tmp_path / "out")
    assert result.status == "OK"
    assert result.audit_path.exists()
    assert "multiple-testing" in result.latest_path.read_text(encoding="utf-8")


def test_audit_script_no_orders():
    source = Path("scripts/run_edge_significance_audit.py").read_text(encoding="utf-8")
    assert "order_send" not in source
    assert "v51_demo_executor" not in source
