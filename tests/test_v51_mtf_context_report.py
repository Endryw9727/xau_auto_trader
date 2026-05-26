from pathlib import Path

import pandas as pd

from scripts import run_v51_mtf_context_report as mtf_report


NOW = pd.Timestamp("2026-05-26 12:00:00")


def write_tf_csv(
    data_dir: Path,
    filename: str,
    *,
    rows: int,
    freq: str,
    end: pd.Timestamp = NOW,
    final_close: float = 2500.0,
    step: float = 0.5,
) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    index = pd.date_range(end=end, periods=rows, freq=freq)
    close = [final_close - (rows - 1 - idx) * step for idx in range(rows)]
    data = pd.DataFrame(
        {
            "Date": index,
            "Open": [value - 0.2 for value in close],
            "High": [value + 0.8 for value in close],
            "Low": [value - 0.8 for value in close],
            "Close": close,
            "Volume": [1000] * rows,
        }
    )
    path = data_dir / filename
    data.to_csv(path, index=False)
    return path


def test_v51_mtf_context_report_gestisce_timeframe_mancanti(tmp_path):
    data_dir = tmp_path / "data"
    write_tf_csv(data_dir, "xauusd.csv", rows=180, freq="15min")

    result = mtf_report.run_v51_mtf_context_report(data_dir=data_dir, output_dir=tmp_path / "diagnostics", now=NOW)

    summary = pd.read_csv(result.summary_path)
    assert result.status == "OK"
    assert set(summary["timeframe"]) == set(mtf_report.TIMEFRAMES)
    assert summary.loc[summary["timeframe"] == "H1", "status"].iloc[0] == "MISSING"
    assert summary.loc[summary["timeframe"] == "M5", "status"].iloc[0] == "MISSING"


def test_v51_mtf_context_report_genera_report_con_solo_m15(tmp_path):
    data_dir = tmp_path / "data"
    write_tf_csv(data_dir, "xauusd.csv", rows=180, freq="15min")

    result = mtf_report.run_v51_mtf_context_report(data_dir=data_dir, output_dir=tmp_path / "diagnostics", now=NOW)

    summary = pd.read_csv(result.summary_path)
    latest = result.latest_path.read_text(encoding="utf-8")
    assert result.summary_path.exists()
    assert result.latest_path.exists()
    assert summary.loc[summary["timeframe"] == "M15", "status"].iloc[0] == "OK"
    assert "Final bias:" in latest


def test_v51_mtf_context_report_genera_report_con_m15_h1_h4(tmp_path):
    data_dir = tmp_path / "data"
    write_tf_csv(data_dir, "xauusd.csv", rows=220, freq="15min", step=0.3)
    write_tf_csv(data_dir, "xauusd_h1.csv", rows=160, freq="1h", step=0.8)
    write_tf_csv(data_dir, "xauusd_h4.csv", rows=120, freq="4h", step=2.0)

    result = mtf_report.run_v51_mtf_context_report(data_dir=data_dir, output_dir=tmp_path / "diagnostics", now=NOW)

    summary = pd.read_csv(result.summary_path)
    statuses = dict(zip(summary["timeframe"], summary["status"]))
    assert statuses["M15"] == "OK"
    assert statuses["H1"] == "OK"
    assert statuses["H4"] == "OK"
    assert statuses["D1"] in {"OK", "DERIVED"}


def test_v51_mtf_context_report_non_invia_ordini():
    source = Path("scripts/run_v51_mtf_context_report.py").read_text(encoding="utf-8")

    assert "order_send" not in source
    assert "run_v51_demo_execution_once" not in source
    assert "run_v51_live_safe_cycle" not in source


def test_v51_mtf_context_report_produce_bias_finale(tmp_path):
    data_dir = tmp_path / "data"
    write_tf_csv(data_dir, "xauusd.csv", rows=220, freq="15min", step=0.5)
    write_tf_csv(data_dir, "xauusd_h1.csv", rows=160, freq="1h", step=1.0)
    write_tf_csv(data_dir, "xauusd_h4.csv", rows=120, freq="4h", step=2.0)

    result = mtf_report.run_v51_mtf_context_report(data_dir=data_dir, output_dir=tmp_path / "diagnostics", now=NOW)

    summary = pd.read_csv(result.summary_path)
    bias = summary["final_bias"].iloc[0]
    assert bias in {"LONG_BIAS", "SHORT_BIAS", "MIXED", "NO_TRADE_CONTEXT"}
    assert isinstance(summary["final_reason"].iloc[0], str)
    assert len(summary["final_reason"].iloc[0]) > 0


def test_v51_mtf_context_report_produce_support_resistance_summary(tmp_path):
    data_dir = tmp_path / "data"
    write_tf_csv(data_dir, "xauusd.csv", rows=180, freq="15min")

    result = mtf_report.run_v51_mtf_context_report(data_dir=data_dir, output_dir=tmp_path / "diagnostics", now=NOW)

    summary = pd.read_csv(result.summary_path)
    m15 = summary[summary["timeframe"] == "M15"].iloc[0]
    latest = result.latest_path.read_text(encoding="utf-8")
    assert float(m15["recent_swing_high"]) > float(m15["recent_swing_low"])
    assert float(m15["distance_from_support"]) >= 0
    assert "Support / Resistance" in latest


def test_v51_mtf_context_report_exclude_m1_stale(tmp_path):
    data_dir = tmp_path / "data"
    write_tf_csv(data_dir, "xauusd.csv", rows=180, freq="15min")
    write_tf_csv(data_dir / "timeframes", "XAUUSD_M1.csv", rows=180, freq="1min", end=NOW - pd.Timedelta(days=10))

    result = mtf_report.run_v51_mtf_context_report(data_dir=data_dir, output_dir=tmp_path / "diagnostics", now=NOW)

    summary = pd.read_csv(result.summary_path)
    m1 = summary[summary["timeframe"] == "M1"].iloc[0]
    latest = result.latest_path.read_text(encoding="utf-8")
    assert m1["data_status"] == "STALE"
    assert str(m1["used_in_bias"]).lower() == "false"
    assert "M1 file=" in latest
    assert "status=STALE used_in_bias=False" in latest


def test_v51_mtf_context_report_exclude_m5_stale(tmp_path):
    data_dir = tmp_path / "data"
    write_tf_csv(data_dir, "xauusd.csv", rows=180, freq="15min")
    write_tf_csv(data_dir / "timeframes", "XAUUSD_M5.csv", rows=180, freq="5min", end=NOW - pd.Timedelta(days=10))

    result = mtf_report.run_v51_mtf_context_report(data_dir=data_dir, output_dir=tmp_path / "diagnostics", now=NOW)

    summary = pd.read_csv(result.summary_path)
    m5 = summary[summary["timeframe"] == "M5"].iloc[0]
    assert m5["data_status"] == "STALE"
    assert str(m5["used_in_bias"]).lower() == "false"


def test_v51_mtf_context_report_stale_m15_usa_primary_fallback(tmp_path):
    data_dir = tmp_path / "data"
    primary = write_tf_csv(data_dir, "xauusd.csv", rows=180, freq="15min")
    write_tf_csv(data_dir / "timeframes", "XAUUSD_M15.csv", rows=180, freq="15min", end=NOW - pd.Timedelta(days=10))

    result = mtf_report.run_v51_mtf_context_report(data_dir=data_dir, output_dir=tmp_path / "diagnostics", now=NOW)

    summary = pd.read_csv(result.summary_path)
    m15 = summary[summary["timeframe"] == "M15"].iloc[0]
    assert m15["data_status"] == "OK"
    assert str(m15["used_in_bias"]).lower() == "true"
    assert Path(m15["source_file"]) == primary


def test_v51_mtf_context_report_exclude_price_mismatch(tmp_path):
    data_dir = tmp_path / "data"
    write_tf_csv(data_dir, "xauusd.csv", rows=180, freq="15min", final_close=2500.0)
    write_tf_csv(data_dir, "xauusd_h1.csv", rows=120, freq="1h", final_close=3100.0)

    result = mtf_report.run_v51_mtf_context_report(data_dir=data_dir, output_dir=tmp_path / "diagnostics", now=NOW)

    summary = pd.read_csv(result.summary_path)
    h1 = summary[summary["timeframe"] == "H1"].iloc[0]
    assert h1["data_status"] == "PRICE_MISMATCH"
    assert str(h1["used_in_bias"]).lower() == "false"
    assert float(h1["price_gap_from_primary"]) > 0


def test_v51_mtf_context_report_h1_h4_validi_usati_nel_bias(tmp_path):
    data_dir = tmp_path / "data"
    write_tf_csv(data_dir, "xauusd.csv", rows=220, freq="15min", final_close=2500.0)
    write_tf_csv(data_dir, "xauusd_h1.csv", rows=160, freq="1h", final_close=2501.0)
    write_tf_csv(data_dir, "xauusd_h4.csv", rows=120, freq="4h", final_close=2502.0)

    result = mtf_report.run_v51_mtf_context_report(data_dir=data_dir, output_dir=tmp_path / "diagnostics", now=NOW)

    summary = pd.read_csv(result.summary_path)
    h1 = summary[summary["timeframe"] == "H1"].iloc[0]
    h4 = summary[summary["timeframe"] == "H4"].iloc[0]
    assert h1["data_status"] == "OK"
    assert h4["data_status"] == "OK"
    assert str(h1["used_in_bias"]).lower() == "true"
    assert str(h4["used_in_bias"]).lower() == "true"


def test_v51_mtf_context_report_tutto_stale_no_trade_context(tmp_path):
    data_dir = tmp_path / "data"
    old = NOW - pd.Timedelta(days=10)
    write_tf_csv(data_dir, "xauusd.csv", rows=180, freq="15min", end=old)
    write_tf_csv(data_dir, "xauusd_h1.csv", rows=120, freq="1h", end=old)
    write_tf_csv(data_dir, "xauusd_h4.csv", rows=120, freq="4h", end=old)

    result = mtf_report.run_v51_mtf_context_report(data_dir=data_dir, output_dir=tmp_path / "diagnostics", now=NOW)

    summary = pd.read_csv(result.summary_path)
    assert result.final_bias == "NO_TRADE_CONTEXT"
    assert summary["final_bias"].iloc[0] == "NO_TRADE_CONTEXT"
    assert "Not enough aligned multi-timeframe context" in summary["final_reason"].iloc[0]
