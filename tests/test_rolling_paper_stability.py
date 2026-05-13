import pandas as pd

from scripts import analyze_rolling_paper_stability as script
from src.paper import paper_degradation as degradation
from src.paper.paper_monitor import PaperReports


def make_reports() -> PaperReports:
    count = 140
    times = pd.date_range("2025-01-01 09:00:00", periods=count, freq="D")
    pnl = []
    for idx in range(count):
        if 70 <= idx < 100:
            pnl.append(-2.0 if idx % 2 == 0 else 1.0)
        else:
            pnl.append(4.0 if idx % 3 else -2.0)
    trades = pd.DataFrame(
        {
            "strategy_name": ["proxy_hardened_no_worst_hours"] * count,
            "entry_time": times,
            "session": ["LONDON" if idx % 2 == 0 else "NEW YORK" for idx in range(count)],
            "side": ["BUY" if idx % 2 == 0 else "SELL" for idx in range(count)],
            "signal_reason": ["reason_a" if idx % 5 else "reason_b" for idx in range(count)],
            "score": [75 + (idx % 10) for idx in range(count)],
            "pnl_eur": pnl,
        }
    )
    equity = 1000 + trades["pnl_eur"].cumsum()
    return PaperReports(
        trades=trades,
        equity_curve=pd.DataFrame(
            {
                "strategy_name": ["proxy_hardened_no_worst_hours"] * count,
                "entry_time": times,
                "equity_after": equity,
                "drawdown_percent": [0.0] * count,
            }
        ),
        daily_summary=pd.DataFrame(
            {
                "strategy_name": ["proxy_hardened_no_worst_hours"] * count,
                "date": times.normalize(),
                "trades": [1] * count,
                "net_profit": pnl,
            }
        ),
    )


def test_rolling_stability_reports_find_worst_windows():
    rolling, worst = degradation.build_rolling_stability_reports(make_reports())

    assert set(degradation.ROLLING_COLUMNS).issubset(rolling.columns)
    assert set(degradation.WORST_ROLLING_COLUMNS).issubset(worst.columns)
    assert set(worst["window_size"]) == {30, 50, 100}
    assert worst["rolling_profit_factor"].notna().all()
    assert worst["degradation_start_time"].notna().all()


def test_rolling_stability_script_exports(monkeypatch, tmp_path, capsys):
    rolling_path = tmp_path / "rolling.csv"
    worst_path = tmp_path / "worst.csv"

    monkeypatch.setattr(script, "DEFAULT_ROLLING_STABILITY_PATH", rolling_path)
    monkeypatch.setattr(script, "DEFAULT_WORST_ROLLING_WINDOWS_PATH", worst_path)
    monkeypatch.setattr(script, "load_paper_reports", make_reports)

    script.main()
    output = capsys.readouterr().out

    assert rolling_path.exists()
    assert worst_path.exists()
    assert "Rolling Paper Stability" in output
    assert "No strategy was changed" in output


def test_rolling_sources_are_research_only():
    source = open("scripts/analyze_rolling_paper_stability.py", encoding="utf-8").read()
    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
