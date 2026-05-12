import pandas as pd

from src.paper import paper_monitor as monitor


def make_reports() -> monitor.PaperReports:
    strategy = "proxy_hardened_no_worst_hours"
    trades = pd.DataFrame(
        {
            "strategy_name": [strategy] * 6,
            "entry_time": pd.to_datetime(
                [
                    "2025-01-01 09:00:00",
                    "2025-01-02 09:00:00",
                    "2025-01-03 09:00:00",
                    "2025-01-06 09:00:00",
                    "2025-01-07 09:00:00",
                    "2025-01-08 09:00:00",
                ]
            ),
            "session": ["LONDON", "LONDON", "NEW YORK", "LONDON", "NEW YORK", "LONDON"],
            "signal_reason": ["reason 1", "reason 2", "reason 3", "reason 4", "reason 5", "reason 6"],
            "pnl_eur": [10.0, -4.0, 12.0, -3.0, -2.0, 8.0],
        }
    )
    equity = pd.DataFrame(
        {
            "strategy_name": [strategy] * 6,
            "paper_order_id": [f"p-{idx}" for idx in range(6)],
            "entry_time": trades["entry_time"],
            "equity_before": [1000.0, 1010.0, 1006.0, 1018.0, 1015.0, 1013.0],
            "equity_after": [1010.0, 1006.0, 1018.0, 1015.0, 1013.0, 1021.0],
            "running_equity_high": [1010.0, 1010.0, 1018.0, 1018.0, 1018.0, 1021.0],
            "drawdown_eur": [0.0, 4.0, 0.0, 3.0, 5.0, 0.0],
            "drawdown_percent": [0.0, 0.4, 0.0, 0.29, 0.49, 0.0],
            "lot_size": [0.01] * 6,
            "pnl_eur": trades["pnl_eur"],
        }
    )
    daily = pd.DataFrame(
        {
            "strategy_name": [strategy] * 8,
            "date": pd.to_datetime(
                [
                    "2025-01-01",
                    "2025-01-02",
                    "2025-01-03",
                    "2025-01-04",
                    "2025-01-05",
                    "2025-01-06",
                    "2025-01-07",
                    "2025-01-08",
                ]
            ),
            "trades": [1, 1, 1, 0, 0, 1, 1, 1],
            "skipped_trades": [0] * 8,
            "net_profit": [10.0, -4.0, 12.0, 0.0, 0.0, -3.0, -2.0, 8.0],
            "gross_profit": [10.0, 0.0, 12.0, 0.0, 0.0, 0.0, 0.0, 8.0],
            "gross_loss": [0.0, 4.0, 0.0, 0.0, 0.0, 3.0, 2.0, 0.0],
            "ending_equity": [1010.0, 1006.0, 1018.0, 1018.0, 1018.0, 1015.0, 1013.0, 1021.0],
            "max_drawdown_eur": [0.0, 4.0, 0.0, 0.0, 0.0, 3.0, 5.0, 0.0],
            "max_drawdown_percent": [0.0, 0.4, 0.0, 0.0, 0.0, 0.29, 0.49, 0.0],
            "daily_stopped": [False] * 8,
            "positive_day": [True, False, True, False, False, False, False, True],
            "negative_day": [False, True, False, False, False, True, True, False],
        }
    )
    return monitor.PaperReports(trades=trades, equity_curve=equity, daily_summary=daily)


def test_build_monitor_summary_calculates_required_metrics():
    summary = monitor.build_monitor_summary(make_reports())
    row = summary.iloc[0]

    assert set(monitor.MONITOR_SUMMARY_COLUMNS).issubset(summary.columns)
    assert row["strategy_name"] == "proxy_hardened_no_worst_hours"
    assert row["equity_current"] == 1021.0
    assert row["total_profit_loss"] == 21.0
    assert row["total_trades"] == 6
    assert row["trades_today"] == 1
    assert row["trades_week"] == 3
    assert row["trades_month"] == 6
    assert row["profit_factor_total"] > 1.0
    assert row["win_rate_total"] == 50.0
    assert row["max_consecutive_losses"] == 2
    assert row["current_consecutive_losses"] == 0
    assert row["last_session"] == "LONDON"
    assert row["last_result"] == "WIN"


def test_evaluate_daily_status_warning_and_stop_rules():
    base = {
        "current_drawdown_pct": 0.0,
        "max_drawdown_pct": 9.0,
        "total_trades": 60,
        "profit_factor_last_30": 1.2,
        "profit_factor_last_50": 1.1,
        "current_consecutive_losses": 0,
        "daily_loss_current_pct": 0.0,
        "weekly_loss_current_pct": 0.0,
    }
    assert monitor.evaluate_daily_status(base)[0] == "WARNING"

    stop = base | {"max_drawdown_pct": 13.0}
    status, _warnings, stops = monitor.evaluate_daily_status(stop)

    assert status == "STOP"
    assert any("drawdown" in reason for reason in stops)


def test_monitor_sources_are_research_only():
    source = open("src/paper/paper_monitor.py", encoding="utf-8").read()
    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
