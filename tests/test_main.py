from src.main import REPORT_DIR, RAW_DATA_PATH, build_backtest_config, build_strategy_config
from src.settings import (
    AppSettings,
    BacktestSettings,
    SessionSettings,
    FilterSettings,
    RiskSettings,
    StrategySettings,
    TradingSettings,
)


def test_main_paths_are_defined():
    assert str(RAW_DATA_PATH) == "data/raw/xauusd.csv"
    assert str(REPORT_DIR) == "reports/backtests"


def test_main_builds_configs_from_settings():
    settings = AppSettings(
        trading=TradingSettings(
            symbol="XAUUSD",
            live_mode=False,
            base_timeframe="30m",
            confirmation_timeframes=["1h"],
        ),
        strategy=StrategySettings(
            atr_multiplier_sl=1.2,
            atr_multiplier_tp=2.8,
            rsi_buy_max=65.0,
            rsi_sell_min=35.0,
        ),
        risk=RiskSettings(
            risk_per_trade=0.004,
            max_risk_per_trade=0.008,
            max_daily_loss=0.015,
            max_open_trades=3,
            max_consecutive_losses=4,
            min_risk_reward=1.8,
            value_per_point=2.0,
        ),
        sessions=SessionSettings(
            enabled_sessions=["Asia", "New York", "Off Session"],
        ),
        filters=FilterSettings(
            avoid_high_impact_news=True,
            max_spread_points=25,
            use_adx_filter=True,
            min_adx=22,
        ),
        backtest=BacktestSettings(
            initial_balance=2500,
            commission_per_trade=0.5,
            slippage_points=0.2,
            warmup_candles=180,
            rolling_window_candles=300,
        ),
    )

    strategy_config = build_strategy_config(settings)
    backtest_config = build_backtest_config(settings)

    assert strategy_config.timeframe == "30m"
    assert strategy_config.min_adx == 22
    assert strategy_config.atr_multiplier_sl == 1.2
    assert backtest_config.risk_per_trade == 0.004
    assert backtest_config.max_risk_per_trade == 0.008
    assert backtest_config.max_open_trades == 3
    assert backtest_config.warmup_candles == 180
    assert backtest_config.rolling_window_candles == 300
