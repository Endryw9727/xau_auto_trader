from pathlib import Path

import pandas as pd

from scripts import run_v51_diagnostic_report as diagnostic


def write_ohlcv_csv(path: Path, rows: int = 260) -> Path:
    index = pd.date_range("2026-05-20 00:00:00", periods=rows, freq="15min")
    data = pd.DataFrame(
        {
            "Date": index,
            "Open": [2400.0 + idx * 0.1 for idx in range(rows)],
            "High": [2400.5 + idx * 0.1 for idx in range(rows)],
            "Low": [2399.5 + idx * 0.1 for idx in range(rows)],
            "Close": [2400.2 + idx * 0.1 for idx in range(rows)],
            "Volume": [1000] * rows,
        }
    )
    data.to_csv(path, index=False)
    return path


def write_ohlcv_csv_until(path: Path, latest: str, rows: int = 260) -> Path:
    index = pd.date_range(end=pd.Timestamp(latest), periods=rows, freq="15min")
    data = pd.DataFrame(
        {
            "Date": index,
            "Open": [2400.0 + idx * 0.1 for idx in range(rows)],
            "High": [2400.5 + idx * 0.1 for idx in range(rows)],
            "Low": [2399.5 + idx * 0.1 for idx in range(rows)],
            "Close": [2400.2 + idx * 0.1 for idx in range(rows)],
            "Volume": [1000] * rows,
        }
    )
    data.to_csv(path, index=False)
    return path


def sample_decision_log() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "signal_id": "V51-202605201000-BUY",
                "candle_time": "2026-05-20T10:00:00",
                "session": "LONDON",
                "side": "BUY",
                "decision": "ACCEPTED",
                "score": 82.0,
                "score_gap": 20.0,
                "entry_price": 2400.0,
                "stop_loss": 2398.8,
                "take_profit": 2401.5,
                "risk_reward": 1.25,
                "lot_size": 0.01,
                "spread_cost": 0.0,
                "slippage_estimate": 0.1,
                "reason": "V51 demo intraday signal accepted",
            },
            {
                "signal_id": "V51-202605201015-SELL",
                "candle_time": "2026-05-20T10:15:00",
                "session": "NEW YORK",
                "side": "SELL",
                "decision": "REJECTED",
                "score": 58.0,
                "score_gap": 10.0,
                "entry_price": 2401.0,
                "stop_loss": 2402.2,
                "take_profit": 2399.5,
                "risk_reward": 1.25,
                "lot_size": 0.01,
                "spread_cost": 0.0,
                "slippage_estimate": 0.1,
                "reason": "score 58.0 below 60.0",
            },
            {
                "signal_id": "V51-202605201030-BUY",
                "candle_time": "2026-05-20T10:30:00",
                "session": "NEW YORK",
                "side": "BUY",
                "decision": "REJECTED",
                "score": 72.0,
                "score_gap": 2.0,
                "entry_price": 2402.0,
                "stop_loss": 2400.8,
                "take_profit": 2403.5,
                "risk_reward": 1.25,
                "lot_size": 0.01,
                "spread_cost": 0.0,
                "slippage_estimate": 0.1,
                "reason": "score gap 2.0 below 4.0",
            },
            {
                "signal_id": "V51-202605201045-SELL",
                "candle_time": "2026-05-20T10:45:00",
                "session": "NEW YORK",
                "side": "SELL",
                "decision": "REJECTED",
                "score": 55.0,
                "score_gap": 9.0,
                "entry_price": 2403.0,
                "stop_loss": 2404.2,
                "take_profit": 2401.5,
                "risk_reward": 1.25,
                "lot_size": 0.01,
                "spread_cost": 0.0,
                "slippage_estimate": 0.1,
                "reason": "score 58.0 below 60.0",
            },
        ]
    )


def recent_decision_log(*, latest_has_candidate: bool = True, include_future: bool = False) -> pd.DataFrame:
    rows = [
        {
            "signal_id": "V51-202606030200-SELL",
            "candle_time": "2026-06-03T02:00:00",
            "session": "NEW YORK",
            "side": "SELL",
            "decision": "ACCEPTED",
            "score": 82.0,
            "score_gap": 20.0,
            "entry_price": 2400.0,
            "stop_loss": 2401.2,
            "take_profit": 2398.5,
            "risk_reward": 1.25,
            "lot_size": 0.01,
            "spread_cost": 0.0,
            "slippage_estimate": 0.1,
            "reason": "V51 demo intraday signal accepted",
        },
        {
            "signal_id": "V51-202606030215-SELL" if latest_has_candidate else "V51-202606030215-NO_TRADE",
            "candle_time": "2026-06-03T02:15:00",
            "session": "NEW YORK",
            "side": "SELL" if latest_has_candidate else "",
            "decision": "ACCEPTED" if latest_has_candidate else "NO_TRADE",
            "score": 81.0 if latest_has_candidate else 0.0,
            "score_gap": 18.0 if latest_has_candidate else 0.0,
            "entry_price": 2399.8 if latest_has_candidate else None,
            "stop_loss": 2401.0 if latest_has_candidate else None,
            "take_profit": 2398.3 if latest_has_candidate else None,
            "risk_reward": 1.25 if latest_has_candidate else None,
            "lot_size": 0.01,
            "spread_cost": 0.0,
            "slippage_estimate": 0.1,
            "reason": "V51 demo intraday signal accepted" if latest_has_candidate else "V51 no directional score candidate",
        },
    ]
    if include_future:
        rows.append(
            {
                "signal_id": "V51-202606030230-SELL",
                "candle_time": "2026-06-03T02:30:00",
                "session": "NEW YORK",
                "side": "SELL",
                "decision": "ACCEPTED",
                "score": 90.0,
                "score_gap": 25.0,
                "entry_price": 2399.0,
                "stop_loss": 2400.2,
                "take_profit": 2397.5,
                "risk_reward": 1.25,
                "lot_size": 0.01,
                "spread_cost": 0.0,
                "slippage_estimate": 0.1,
                "reason": "V51 demo intraday signal accepted",
            }
        )
    return pd.DataFrame(rows)


def test_v51_diagnostic_report_crea_report_con_dati_validi(tmp_path, monkeypatch):
    csv_path = write_ohlcv_csv(tmp_path / "xauusd.csv")
    monkeypatch.setattr(diagnostic, "build_demo_intraday_decision_log", lambda *_args, **_kwargs: sample_decision_log())

    result = diagnostic.run_v51_diagnostic_report(csv_path=csv_path, output_dir=tmp_path / "diagnostics", candles=200)

    assert result.status == "OK"
    assert result.summary_path.exists()
    assert result.rejections_path.exists()
    assert result.latest_path.exists()
    summary = pd.read_csv(result.summary_path)
    assert int(summary.iloc[0]["candles_analyzed"]) == 4
    assert int(summary.iloc[0]["candidate_count"]) == 4
    assert int(summary.iloc[0]["accepted_candidates"]) == 1
    assert "Last 10 candidates" in result.latest_path.read_text(encoding="utf-8")
    assert result.probe_path.exists()
    assert result.probe_latest_path.exists()


def test_v51_diagnostic_report_non_invia_ordini():
    source = Path("scripts/run_v51_diagnostic_report.py").read_text(encoding="utf-8")

    assert "order_send" not in source
    assert "run_v51_demo_execution_once" not in source


def test_v51_diagnostic_report_gestisce_csv_mancante(tmp_path):
    result = diagnostic.run_v51_diagnostic_report(csv_path=tmp_path / "missing.csv", output_dir=tmp_path / "diagnostics")

    assert result.status == "ERROR"
    summary = pd.read_csv(result.summary_path)
    assert summary.iloc[0]["status"] == "ERROR"
    assert "CSV file not found" in summary.iloc[0]["reason"]


def test_v51_diagnostic_report_gestisce_dataset_insufficiente(tmp_path):
    csv_path = write_ohlcv_csv(tmp_path / "short.csv", rows=20)

    result = diagnostic.run_v51_diagnostic_report(csv_path=csv_path, output_dir=tmp_path / "diagnostics")

    assert result.status == "INSUFFICIENT_DATA"
    summary = pd.read_csv(result.summary_path)
    assert summary.iloc[0]["status"] == "INSUFFICIENT_DATA"
    assert "dataset insufficient" in summary.iloc[0]["reason"]


def test_v51_diagnostic_report_produce_top_rejection_reasons(tmp_path, monkeypatch):
    csv_path = write_ohlcv_csv(tmp_path / "xauusd.csv")
    monkeypatch.setattr(diagnostic, "build_demo_intraday_decision_log", lambda *_args, **_kwargs: sample_decision_log())

    result = diagnostic.run_v51_diagnostic_report(csv_path=csv_path, output_dir=tmp_path / "diagnostics", candles=200)

    summary = pd.read_csv(result.summary_path)
    rejections = pd.read_csv(result.rejections_path)
    assert "score 58.0 below 60.0 (2)" in summary.iloc[0]["top_rejection_reasons"]
    assert len(rejections) == 3


def test_v51_diagnostic_latest_mostra_latest_candle_del_csv_corrente(tmp_path, monkeypatch):
    csv_path = write_ohlcv_csv_until(tmp_path / "xauusd.csv", "2026-06-03 02:15:00")
    monkeypatch.setattr(diagnostic, "build_demo_intraday_decision_log", lambda *_args, **_kwargs: recent_decision_log())

    result = diagnostic.run_v51_diagnostic_report(csv_path=csv_path, output_dir=tmp_path / "diagnostics", candles=200)

    latest_text = result.latest_path.read_text(encoding="utf-8")
    summary = pd.read_csv(result.summary_path)
    assert "Latest candle time: 2026-06-03T02:15:00" in latest_text
    assert str(summary.iloc[0]["latest_candle_time"]).startswith("2026-06-03T02:15:00")


def test_v51_live_candidate_probe_mostra_candidati_recenti(tmp_path, monkeypatch):
    csv_path = write_ohlcv_csv_until(tmp_path / "xauusd.csv", "2026-06-03 02:15:00")
    monkeypatch.setattr(diagnostic, "build_demo_intraday_decision_log", lambda *_args, **_kwargs: recent_decision_log())

    result = diagnostic.run_v51_diagnostic_report(csv_path=csv_path, output_dir=tmp_path / "diagnostics", candles=200)

    probe = pd.read_csv(result.probe_path)
    row = probe.iloc[0]
    assert int(row["candidates_generated_last_20"]) == 2
    assert bool(row["latest_candle_had_candidate"]) is True
    assert str(row["selected_candidate_time"]) not in {"", "nan"}
    assert "latest candle candidate accepted" in row["rejection_reason"]


def test_v51_live_candidate_probe_spiega_mancanza_candidate_latest(tmp_path, monkeypatch):
    csv_path = write_ohlcv_csv_until(tmp_path / "xauusd.csv", "2026-06-03 02:15:00")
    monkeypatch.setattr(
        diagnostic,
        "build_demo_intraday_decision_log",
        lambda *_args, **_kwargs: recent_decision_log(latest_has_candidate=False),
    )

    result = diagnostic.run_v51_diagnostic_report(csv_path=csv_path, output_dir=tmp_path / "diagnostics", candles=200)

    row = pd.read_csv(result.probe_path).iloc[0]
    assert bool(row["latest_candle_had_candidate"]) is False
    assert "no setup" in row["rejection_reason"]
    assert "candidate generated but not latest" in row["rejection_reason"]


def test_v51_live_candidate_probe_non_accetta_candidate_futuro(tmp_path, monkeypatch):
    csv_path = write_ohlcv_csv_until(tmp_path / "xauusd.csv", "2026-06-03 02:15:00")
    monkeypatch.setattr(
        diagnostic,
        "build_demo_intraday_decision_log",
        lambda *_args, **_kwargs: recent_decision_log(latest_has_candidate=False, include_future=True),
    )

    result = diagnostic.run_v51_diagnostic_report(csv_path=csv_path, output_dir=tmp_path / "diagnostics", candles=200)

    row = pd.read_csv(result.probe_path).iloc[0]
    assert str(row["selected_candidate_time"]) in {"", "nan"}
    assert "V51-202606030230" in row["nearest_candidate_after_latest"]
    assert "diagnostic only, never tradable" in result.probe_latest_path.read_text(encoding="utf-8")
