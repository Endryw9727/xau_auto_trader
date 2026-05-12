import pandas as pd

from scripts import analyze_paper_readiness_final as script
from src.paper.paper_engine import PaperTradingConfig


def make_config() -> PaperTradingConfig:
    return PaperTradingConfig(
        strategy_name="proxy_hardened_no_worst_hours",
        backup_strategy="proxy_hardened_no_worst_hours_high_margin",
        symbol="XAUUSD",
        base_timeframe="15m",
        live_mode=False,
        paper_mode=True,
        initial_equity=1000.0,
        min_lot=0.01,
        lot_step=0.01,
        equity_step=1000.0,
        max_lot=0.10,
        commission_per_001_lot_per_side=0.04,
        spread_pips=0.0,
        slippage_pips=0.0,
        conservative_slippage_pips=0.1,
        max_trades_per_day=2,
        max_daily_loss_pct=3.0,
        max_consecutive_losses_day=2,
        max_consecutive_losses_total_warning=8,
        max_drawdown_warning_pct=8.0,
        max_drawdown_stop_pct=12.0,
        min_score_required=72.0,
        no_trade_after_daily_stop=True,
    )


def make_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "strategy_name": "proxy_hardened_no_worst_hours",
                "ending_equity": 2597.50,
                "net_profit": 1597.50,
                "profit_factor_net": 1.354,
                "max_dd_pct": 10.50,
                "max_dd_eur": 160.0,
                "total_trades": 894,
                "trades_per_day": 0.679,
                "win_rate": 38.0,
                "expectancy": 1.78,
                "max_consecutive_losses": 10,
                "worst_day": -30.0,
                "worst_week": -60.0,
                "worst_month": -90.0,
                "months_positive": 14,
                "months_negative": 4,
                "no_trade_days": 300,
                "max_no_trade_days": 6,
                "drawdown_over_8_pct": True,
                "drawdown_over_10_pct": True,
                "drawdown_over_12_pct": False,
            },
            {
                "strategy_name": "proxy_hardened_no_worst_hours_high_margin",
                "ending_equity": 2116.96,
                "net_profit": 1116.96,
                "profit_factor_net": 1.388,
                "max_dd_pct": 7.34,
                "max_dd_eur": 80.0,
                "total_trades": 702,
                "trades_per_day": 0.533,
                "win_rate": 38.0,
                "expectancy": 1.59,
                "max_consecutive_losses": 10,
                "worst_day": -20.0,
                "worst_week": -40.0,
                "worst_month": -60.0,
                "months_positive": 14,
                "months_negative": 4,
                "no_trade_days": 400,
                "max_no_trade_days": 8,
                "drawdown_over_8_pct": False,
                "drawdown_over_10_pct": False,
                "drawdown_over_12_pct": False,
            },
        ]
    )


def test_readiness_helpers_select_main_candidate():
    summary = script.prepare_summary(make_summary())
    main = script.row_for_strategy(summary, "proxy_hardened_no_worst_hours")
    backup = script.row_for_strategy(summary, "proxy_hardened_no_worst_hours_high_margin")

    assert script.is_ready_for_paper(main) is True
    assert "Ready for controlled paper study" in script.build_paper_readiness_text(main, backup, make_config())
    assert "drawdown reaches 12.0%" in script.build_stop_conditions(make_config())
    assert "explicit user approval" in script.build_transition_conditions()


def test_analyze_paper_readiness_final_script_runs(monkeypatch, tmp_path, capsys):
    summary_path = tmp_path / "paper_summary.csv"
    make_summary().to_csv(summary_path, index=False)

    monkeypatch.setattr(script, "DEFAULT_PAPER_SUMMARY_PATH", summary_path)
    monkeypatch.setattr(script, "load_paper_trading_config", lambda: make_config())

    script.main()
    output = capsys.readouterr().out

    assert "Final Paper Readiness" in output
    assert "Recommended paper candidate" in output
    assert "Not ready for live" in output
    assert "No strategy was promoted automatically." in output


def test_paper_readiness_script_is_research_only():
    source = open("scripts/analyze_paper_readiness_final.py", encoding="utf-8").read()
    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
