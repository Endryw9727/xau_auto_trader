from pathlib import Path

import pandas as pd
import pytest

from scripts import analyze_v50_fast_loss_proxies as proxy_script
from src.strategy_lab.strategy_v50_candidates import FINAL_BALANCED_STRATEGY_NAME
from src.strategy_lab.v50_fast_loss_proxies import (
    PROXY_ANALYSIS_COLUMNS,
    PROXY_CANDIDATE_COLUMNS,
    build_fast_loss_proxy_analysis,
    build_fast_loss_proxy_candidates,
    build_fast_loss_proxy_dataset,
    export_fast_loss_proxy_reports,
    validate_no_leakage_columns,
)


def make_trades() -> pd.DataFrame:
    pnl = [-7.0, 12.0, -5.0, -4.0, 10.0, -6.0, 9.0, -3.0, 8.0, -2.0]
    bars = [1, 4, 8, 1, 3, 12, 5, 0, 4, 9]
    return pd.DataFrame(
        {
            "strategy_name": [FINAL_BALANCED_STRATEGY_NAME] * len(pnl),
            "entry_time": pd.date_range("2025-01-01 09:00:00", periods=len(pnl), freq="4h"),
            "exit_time": pd.date_range("2025-01-01 10:00:00", periods=len(pnl), freq="4h"),
            "side": ["BUY", "BUY", "SELL", "BUY", "SELL", "SELL", "BUY", "BUY", "SELL", "SELL"],
            "side_label": ["LONG", "LONG", "SHORT", "LONG", "SHORT", "SHORT", "LONG", "LONG", "SHORT", "SHORT"],
            "session": ["LONDON", "NEW YORK", "LONDON", "LONDON", "ASIA", "LONDON", "NEW YORK", "LONDON", "ASIA", "LONDON"],
            "pnl": pnl,
            "profit_loss": pnl,
            "bars_in_trade": bars,
            "score_long": [72, 84, 25, 73, 35, 30, 88, 74, 25, 40],
            "score_short": [20, 30, 78, 25, 82, 76, 25, 20, 80, 72],
            "signal_reason": ["V50 test | mode=base"] * len(pnl),
        }
    )


def make_market_data() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=80, freq="h")
    close = pd.Series(range(len(dates)), dtype=float) + 100.0
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 2.0,
            "Low": close - 2.0,
            "Close": close + 1.0,
            "Volume": [1.0] * len(dates),
        },
        index=dates,
    )


def test_fast_loss_proxy_reports_use_entry_known_candidates(tmp_path):
    proxy_data = build_fast_loss_proxy_dataset(make_trades(), market_data=make_market_data())
    analysis = build_fast_loss_proxy_analysis(proxy_data)
    candidates = build_fast_loss_proxy_candidates(proxy_data)
    analysis_path, candidates_path = export_fast_loss_proxy_reports(
        analysis,
        candidates,
        tmp_path / "analysis.csv",
        tmp_path / "candidates.csv",
    )

    assert {"fast_loss_0_1", "winning_trade", "normal_loss", "longer_trade"}.issubset(set(analysis["group_name"]))
    assert set(PROXY_ANALYSIS_COLUMNS).issubset(analysis.columns)
    assert set(PROXY_CANDIDATE_COLUMNS).issubset(candidates.columns)
    assert candidates["leakage_safe"].all()
    validate_no_leakage_columns(candidates["filter_column"].unique().tolist())
    assert analysis_path.exists()
    assert candidates_path.exists()


def test_fast_loss_proxy_script_runs_and_exports(monkeypatch, tmp_path, capsys):
    analysis_path = tmp_path / "fast_loss_proxy_analysis.csv"
    candidates_path = tmp_path / "fast_loss_proxy_candidates.csv"

    monkeypatch.setattr(proxy_script, "DEFAULT_FAST_LOSS_PROXY_ANALYSIS_PATH", analysis_path)
    monkeypatch.setattr(proxy_script, "DEFAULT_FAST_LOSS_PROXY_CANDIDATES_PATH", candidates_path)
    monkeypatch.setattr(proxy_script, "RAW_DATA_PATH", tmp_path / "missing.csv")
    monkeypatch.setattr(proxy_script, "load_loss_trade_report", lambda: make_trades())

    proxy_script.main()
    output = capsys.readouterr().out

    assert analysis_path.exists()
    assert candidates_path.exists()
    assert "V50 Fast Loss Proxies" in output
    assert "No strategy was promoted automatically." in output


def test_fast_loss_proxy_leakage_validation_rejects_future_columns():
    for column in ["pnl", "exit_time", "bars_in_trade", "trade_result", "profit_factor", "max_drawdown"]:
        with pytest.raises(ValueError):
            validate_no_leakage_columns([column])


def test_v50_fast_loss_proxy_sources_are_research_only():
    checked_files = [
        Path("src/strategy_lab/v50_fast_loss_proxies.py"),
        Path("scripts/analyze_v50_fast_loss_proxies.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
