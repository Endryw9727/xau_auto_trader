import pandas as pd

from src.paper import defensive_mode_engine as engine
from src.paper.paper_engine import PaperTradingConfig
from src.paper.paper_monitor import PaperReports


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


def make_candidate_rows(count: int = 80) -> pd.DataFrame:
    rows = []
    for idx in range(count):
        entry = pd.Timestamp("2025-01-01 09:00:00") + pd.Timedelta(days=idx)
        price_points = 4.0 if idx % 3 else -2.0
        rows.append(
            {
                "strategy_name": "proxy_hardened_no_worst_hours",
                "paper_order_id": f"main-{idx}",
                "entry_time": entry,
                "exit_time": entry + pd.Timedelta(hours=1),
                "side": "BUY",
                "session": "LONDON",
                "score": 80.0,
                "price_points": price_points,
                "signal_reason": "main",
            }
        )
        if idx % 2 == 0:
            rows.append(
                {
                    "strategy_name": "proxy_hardened_no_worst_hours_high_margin",
                    "paper_order_id": f"hm-{idx}",
                    "entry_time": entry,
                    "exit_time": entry + pd.Timedelta(hours=1),
                    "side": "BUY",
                    "session": "LONDON",
                    "score": 85.0,
                    "price_points": price_points * 0.8,
                    "signal_reason": "high_margin",
                }
            )
    return pd.DataFrame(rows)


def make_reports() -> PaperReports:
    trades = make_candidate_rows()
    return PaperReports(
        trades=trades,
        equity_curve=pd.DataFrame(),
        daily_summary=pd.DataFrame(
            {
                "strategy_name": ["proxy_hardened_no_worst_hours"] * 100,
                "date": pd.date_range("2025-01-01", periods=100, freq="D"),
                "trades": [1] * 100,
            }
        ),
    )


def test_decide_mode_from_state_rules():
    normal = engine.decide_mode_from_state(
        engine.ModeState(50, 1.2, 50, 7.0, 4, 0.0, 1000.0, 1000.0)
    )
    defensive = engine.decide_mode_from_state(
        engine.ModeState(50, 1.05, 50, 9.0, 5, 0.0, 1000.0, 1100.0)
    )
    pause = engine.decide_mode_from_state(
        engine.ModeState(50, 0.95, 50, 13.0, 11, 9.0, 900.0, 1100.0)
    )

    assert normal.mode == engine.MODE_NORMAL
    assert defensive.mode == engine.MODE_DEFENSIVE
    assert pause.mode == engine.MODE_PAUSE


def test_dynamic_defensive_simulation_contains_all_variants():
    summary, timeline, audit = engine.run_dynamic_defensive_paper_simulation(make_reports(), make_config())

    assert set(engine.SUMMARY_COLUMNS).issubset(summary.columns)
    assert set(engine.TIMELINE_COLUMNS).issubset(timeline.columns)
    assert set(engine.AUDIT_COLUMNS).issubset(audit.columns)
    assert {
        engine.VARIANT_MAIN_ALWAYS,
        engine.VARIANT_HIGH_MARGIN_ALWAYS,
        engine.VARIANT_DYNAMIC,
        engine.VARIANT_DYNAMIC_NY18,
    }.issubset(set(summary["variant_name"]))
    assert summary["allow_live"].eq(False).all()


def test_dynamic_defensive_sources_are_research_only():
    source = open("src/paper/defensive_mode_engine.py", encoding="utf-8").read()
    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
