from pathlib import Path

import pandas as pd

from scripts.run_v50_edge_filter_sweep import parse_args
from src.backtesting.backtester import BacktestConfig, BacktestResult
from src.backtesting.metrics import BacktestMetrics
from src.strategy.rules import StrategyConfig
from src.strategy.signals import TradingSignal
from src.strategy_lab import v50_edge_filter_sweep as sweep


def make_sweep_data(rows: int = 12) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01 00:00:00", periods=rows, freq="15min")
    close = [2350.0 + index * 0.2 for index in range(rows)]
    return pd.DataFrame(
        {
            "Open": [value - 0.1 for value in close],
            "High": [value + 0.8 for value in close],
            "Low": [value - 0.8 for value in close],
            "Close": close,
            "Volume": [1000] * rows,
        },
        index=dates,
    )


def make_result(total_trades: int, net_profit: float) -> BacktestResult:
    losses = total_trades // 2
    wins = total_trades - losses
    return BacktestResult(
        trades=pd.DataFrame(),
        metrics=BacktestMetrics(
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            breakeven=0,
            win_rate=wins / total_trades * 100 if total_trades else 0.0,
            net_profit=net_profit,
            profit_factor=1.2 if net_profit > 0 else 0.8 if total_trades else 0.0,
            average_win=2.0,
            average_loss=-1.0,
            expectancy=net_profit / total_trades if total_trades else 0.0,
            max_drawdown=10.0 if total_trades else 0.0,
            max_consecutive_wins=2,
            max_consecutive_losses=3,
        ),
        final_balance=1000.0 + net_profit,
    )


def test_build_v50_edge_filter_variants_includes_required_names():
    variants = sweep.build_v50_edge_filter_variants()
    names = [variant.variant_name for variant in variants]

    assert names == list(sweep.VARIANT_NAMES)
    assert len(names) == len(set(names))


def test_v50_edge_filter_signal_generator_blocks_disallowed_side(monkeypatch):
    def fake_signal(_df, config):
        return TradingSignal(
            timestamp=pd.Timestamp("2025-01-01 10:00:00").to_pydatetime(),
            symbol=config.symbol,
            timeframe=config.timeframe,
            side="SELL",
            entry_price=2350.0,
            stop_loss=2351.0,
            take_profit=2348.0,
            risk_reward=2.0,
            confidence=80.0,
            reason="V50 Pine technical approximation | Side=SELL | score=80.0 | opposite_score=20.0 | session=LONDON",
        )

    monkeypatch.setattr(sweep.strategy_v50_pine, "generate_signal", fake_signal)
    signal_generator = sweep.make_v50_edge_filter_signal_generator(
        sweep.V50EdgeFilterVariant("v50_long_only", allowed_sides=("BUY",)),
    )
    signal = signal_generator(make_sweep_data(), StrategyConfig())

    assert signal.side == "NO_TRADE"
    assert "side=SELL not allowed" in signal.reason


def test_v50_edge_filter_sweep_generates_csv_with_strategy_and_variant(monkeypatch, tmp_path):
    def fake_run_variant(_df, variant, _strategy_config, _backtest_config):
        trade_count = sweep.VARIANT_NAMES.index(variant.variant_name) + 1
        return make_result(trade_count, float(trade_count))

    monkeypatch.setattr(sweep, "run_v50_edge_filter_variant", fake_run_variant)
    output_path = tmp_path / "v50_edge_filter_sweep.csv"

    report = sweep.run_v50_edge_filter_sweep(
        df=make_sweep_data(),
        strategy_config=StrategyConfig(),
        backtest_config=BacktestConfig(warmup_candles=0),
        output_path=output_path,
    )
    exported = pd.read_csv(output_path)

    assert output_path.exists()
    assert set(report["variant_name"]) == set(sweep.VARIANT_NAMES)
    assert set(exported["variant_name"]) == set(sweep.VARIANT_NAMES)
    assert set(exported["strategy_name"]) == {sweep.BASE_STRATEGY_NAME}
    assert {"profit_drawdown_ratio", "variant_name", "strategy_name"}.issubset(exported.columns)


def test_v50_edge_filter_walk_forward_generates_summary_csv(monkeypatch, tmp_path):
    def fake_run_variant(df, variant, _strategy_config, _backtest_config):
        trade_count = 2 if len(df) else 0
        net_profit = 5.0 if variant.variant_name == "v50_base" else -1.0
        return make_result(trade_count, net_profit)

    variants = sweep.build_v50_edge_filter_variants()[:2]
    output_path = tmp_path / "v50_edge_filter_sweep_walk_forward.csv"
    monkeypatch.setattr(sweep, "run_v50_edge_filter_variant", fake_run_variant)

    report = sweep.run_v50_edge_filter_walk_forward(
        df=make_sweep_data(rows=220),
        period="quarter",
        strategy_config=StrategyConfig(),
        backtest_config=BacktestConfig(warmup_candles=0),
        variants=variants,
        output_path=output_path,
    )
    exported = pd.read_csv(output_path)

    assert output_path.exists()
    assert set(exported["variant_name"]) == {variant.variant_name for variant in variants}
    assert set(exported["strategy_name"]) == {sweep.BASE_STRATEGY_NAME}
    assert {"total_periods", "active_periods", "stability_score"}.issubset(report.columns)


def test_v50_edge_filter_sweep_script_options_and_research_safety():
    args = parse_args(["--period", "quarter"])
    source = Path("scripts/run_v50_edge_filter_sweep.py").read_text(encoding="utf-8")

    assert args.period == "quarter"
    assert "live_broker" not in source
    assert "submit_order" not in source
    assert "api_key" not in source.lower()
    assert ".env" not in source
