import pandas as pd

from src.paper import defensive_mode_engine as engine
from tests.test_defensive_mode_engine import make_config


def make_no_lookahead_candidates() -> pd.DataFrame:
    rows = []
    for idx in range(51):
        entry = pd.Timestamp("2025-01-01 09:00:00") + pd.Timedelta(days=idx)
        if idx < 50:
            price_points = 1.0 if idx % 2 else -2.0
        else:
            price_points = 100.0
        rows.append(
            {
                "strategy_name": "proxy_hardened_no_worst_hours",
                "entry_time": entry,
                "exit_time": entry + pd.Timedelta(hours=1),
                "side": "BUY",
                "session": "LONDON",
                "score": 90.0,
                "price_points": price_points,
                "signal_reason": "no lookahead fixture",
            }
        )
    return pd.DataFrame(rows)


def test_trade_mode_uses_only_trades_closed_before_current_trade():
    candidates = engine.prepare_candidate_trades(make_no_lookahead_candidates())
    _summary, timeline, audit = engine.simulate_mode_variant(
        candidates=candidates,
        config=make_config(),
        variant_name=engine.VARIANT_DYNAMIC,
        forced_mode=None,
        filter_new_york_18=False,
        calendar_days=51,
    )

    trade_51_time = pd.Timestamp("2025-02-20 09:00:00")
    row_51 = timeline[timeline["decision_time"] == trade_51_time].iloc[0]

    assert row_51["decision_trade_count"] == 50
    assert row_51["decision_profit_factor_last_50"] < 1.0
    assert row_51["mode"] == engine.MODE_PAUSE
    assert row_51["action"] == "SKIP"
    assert not (pd.to_datetime(audit["entry_time"]) == trade_51_time).any()


def test_no_lookahead_state_ignores_trade_with_future_exit():
    executed = pd.DataFrame(
        [
            {
                "entry_time": pd.Timestamp("2025-01-01 09:00:00"),
                "exit_time": pd.Timestamp("2025-01-03 09:00:00"),
                "pnl_eur": -100.0,
                "equity_before": 1000.0,
                "equity_after": 900.0,
                "running_equity_high": 1000.0,
            }
        ]
    )
    state = engine.build_mode_state(executed, pd.Timestamp("2025-01-02 09:00:00"), initial_equity=1000.0)

    assert state.trade_count == 0
    assert state.current_drawdown_pct == 0.0
