import pandas as pd

from scripts import analyze_recent_paper_degradation as script
from src.paper import paper_degradation as degradation
from src.paper.paper_monitor import PaperReports


def make_trades(strategy_name: str, count: int = 120, multiplier: float = 1.0) -> pd.DataFrame:
    times = pd.date_range("2025-01-01 09:00:00", periods=count, freq="D")
    pnl = []
    for idx in range(count):
        if idx % 5 in (0, 1):
            pnl.append(-3.0 * multiplier)
        else:
            pnl.append(4.0 * multiplier)
    return pd.DataFrame(
        {
            "strategy_name": [strategy_name] * count,
            "entry_time": times,
            "session": ["LONDON" if idx % 2 == 0 else "NEW YORK" for idx in range(count)],
            "side": ["BUY" if idx % 3 else "SELL" for idx in range(count)],
            "signal_reason": ["reason_a" if idx % 4 else "reason_b" for idx in range(count)],
            "score": [72 + (idx % 25) for idx in range(count)],
            "volatility_regime": ["normal" if idx % 4 else "high" for idx in range(count)],
            "pnl_eur": pnl,
        }
    )


def make_reports() -> PaperReports:
    main = make_trades("proxy_hardened_no_worst_hours", multiplier=1.0)
    backup = make_trades("proxy_hardened_no_worst_hours_high_margin", multiplier=0.8)
    trades = pd.concat([main, backup], ignore_index=True)
    equity_frames = []
    daily_frames = []
    for strategy_name, group in trades.groupby("strategy_name"):
        equity = 1000 + group["pnl_eur"].cumsum()
        running_high = equity.cummax()
        equity_frames.append(
            pd.DataFrame(
                {
                    "strategy_name": strategy_name,
                    "entry_time": group["entry_time"].values,
                    "equity_after": equity.values,
                    "drawdown_percent": ((running_high - equity) / running_high * 100).values,
                }
            )
        )
        daily_frames.append(
            pd.DataFrame(
                {
                    "strategy_name": strategy_name,
                    "date": group["entry_time"].dt.normalize().values,
                    "trades": [1] * len(group),
                    "net_profit": group["pnl_eur"].values,
                    "ending_equity": equity.values,
                }
            )
        )
    return PaperReports(
        trades=trades,
        equity_curve=pd.concat(equity_frames, ignore_index=True),
        daily_summary=pd.concat(daily_frames, ignore_index=True),
    )


def test_recent_degradation_reports_include_windows_and_breakdowns():
    reports = make_reports()
    summary, breakdown = degradation.build_recent_degradation_reports(reports)

    assert set(degradation.DEGRADATION_COLUMNS).issubset(summary.columns)
    assert set(degradation.BREAKDOWN_REPORT_COLUMNS).issubset(breakdown.columns)
    assert {"last_30_trades", "last_50_trades", "last_year"}.issubset(set(summary["window_label"]))
    assert not breakdown.empty
    assert "volatility_regime" in set(breakdown["group_type"])


def test_main_vs_high_margin_recent_report_compares_both_strategies():
    report = degradation.build_main_vs_high_margin_recent_report(make_reports())

    assert set(degradation.MAIN_VS_COLUMNS).issubset(report.columns)
    assert set(report["strategy_name"]) == {
        "proxy_hardened_no_worst_hours",
        "proxy_hardened_no_worst_hours_high_margin",
    }
    assert report["profit_factor_last_50"].notna().all()


def test_recent_degradation_script_exports(monkeypatch, tmp_path, capsys):
    degradation_path = tmp_path / "recent.csv"
    breakdown_path = tmp_path / "breakdown.csv"
    main_vs_path = tmp_path / "main_vs.csv"

    monkeypatch.setattr(script, "DEFAULT_RECENT_DEGRADATION_PATH", degradation_path)
    monkeypatch.setattr(script, "DEFAULT_RECENT_DEGRADATION_BREAKDOWN_PATH", breakdown_path)
    monkeypatch.setattr(script, "DEFAULT_MAIN_VS_HIGH_MARGIN_RECENT_PATH", main_vs_path)
    monkeypatch.setattr(script, "load_paper_reports", make_reports)

    script.main()
    output = capsys.readouterr().out

    assert degradation_path.exists()
    assert breakdown_path.exists()
    assert main_vs_path.exists()
    assert "Recent Paper Degradation" in output
    assert "No strategy was changed" in output


def test_recent_degradation_sources_are_research_only():
    for path in ["src/paper/paper_degradation.py", "scripts/analyze_recent_paper_degradation.py"]:
        source = open(path, encoding="utf-8").read()
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
