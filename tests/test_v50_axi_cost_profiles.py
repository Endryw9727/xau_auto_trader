import pandas as pd

from src.strategy_lab import v50_cost_aware as cost_aware


def make_trades() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strategy_name": ["v50_proxy_balanced_candidate", "v50_proxy_balanced_candidate"],
            "entry_time": pd.to_datetime(["2025-01-01 09:00:00", "2025-01-02 09:00:00"]),
            "side": ["BUY", "BUY"],
            "session": ["LONDON", "LONDON"],
            "entry_price": [100.0, 100.0],
            "stop_loss": [98.0, 98.0],
            "take_profit": [104.0, 104.0],
            "position_size": [1.0, 1.0],
            "score_long": [80.0, 82.0],
            "score_short": [50.0, 52.0],
            "profit_loss": [1100.0, 100.0],
            "pnl": [1100.0, 100.0],
        }
    )


def test_axi_profiles_are_explicit_and_legacy_profiles_remain():
    profiles = {profile.name: profile for profile in cost_aware.build_cost_profiles()}

    assert set(cost_aware.AXI_REAL_COST_PROFILE_NAMES).issubset(profiles)
    assert "cost_medium" in profiles
    realistic = profiles["axi_pro_realistic"]
    conservative = profiles["axi_pro_conservative"]
    stress = profiles["axi_pro_stress"]

    assert realistic.spread_pips == 0.0
    assert realistic.slippage_pips == 0.0
    assert realistic.commission_per_001_lot_per_side == 0.04
    assert realistic.commission_round_turn_per_001_lot == 0.08
    assert conservative.slippage_pips == 0.1
    assert stress.spread_pips == 0.1
    assert stress.slippage_pips == 0.2
    assert profiles["cost_medium"].is_axi_profile is False


def test_axi_lot_sizing_progression_and_cap():
    config = cost_aware.AxiSizingConfig(max_lot=0.10)

    assert cost_aware.lot_size_for_equity(1000.0, config) == 0.01
    assert cost_aware.lot_size_for_equity(1999.99, config) == 0.01
    assert cost_aware.lot_size_for_equity(2000.0, config) == 0.02
    assert cost_aware.lot_size_for_equity(3000.0, config) == 0.03
    assert cost_aware.lot_size_for_equity(20000.0, config) == 0.10


def test_axi_cost_application_uses_lot_progression():
    profile = {profile.name: profile for profile in cost_aware.build_cost_profiles()}["axi_pro_realistic"]
    trades = cost_aware.apply_cost_profile_to_trades(
        make_trades(),
        profile,
        sizing_config=cost_aware.AxiSizingConfig(),
    )

    assert list(trades["lot_size"]) == [0.01, 0.02]
    assert list(trades["commission_cost"].round(2)) == [0.08, 0.16]
    assert trades["spread_cost"].sum() == 0.0
    assert trades["slippage_cost"].sum() == 0.0
    assert round(float(trades["net_profit_loss"].sum()), 2) == 1199.76
