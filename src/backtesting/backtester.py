"""
Simple OHLCV backtester.

This backtester:
- adds indicators
- generates signals candle by candle
- validates signals with the risk manager
- simulates SL/TP execution on future candles
- records closed trades
- calculates metrics

This is not live trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.backtesting.metrics import BacktestMetrics, calculate_metrics, metrics_to_dict
from src.risk.risk_manager import AccountState, RiskConfig, evaluate_signal_risk, from_trading_signal
from src.strategy.indicators import add_all_core_indicators
from src.strategy.rules import StrategyConfig
from src.strategy.signals import generate_signal


@dataclass(frozen=True)
class BacktestConfig:
    """Backtest configuration."""

    initial_balance: float = 1000.0
    risk_per_trade: float = 0.005
    max_daily_loss: float = 0.02
    max_open_trades: int = 1
    max_consecutive_losses: int = 3
    min_risk_reward: float = 2.0
    value_per_point: float = 1.0
    commission_per_trade: float = 0.0
    slippage_points: float = 0.0
    warmup_candles: int = 220


@dataclass(frozen=True)
class BacktestResult:
    """Backtest result."""

    trades: pd.DataFrame
    metrics: BacktestMetrics
    final_balance: float


def run_backtest(
    df: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    backtest_config: BacktestConfig | None = None,
) -> BacktestResult:
    """
    Run a simple backtest on OHLCV data.

    Assumption:
    - one position at a time
    - entry happens at signal close price
    - SL/TP checked on following candles
    """
    if strategy_config is None:
        strategy_config = StrategyConfig()

    if backtest_config is None:
        backtest_config = BacktestConfig()

    _validate_ohlcv(df)

    if len(df) <= backtest_config.warmup_candles:
        raise ValueError("Not enough candles for backtest warmup")

    data = add_all_core_indicators(df)
    balance = backtest_config.initial_balance
    trades: list[dict] = []
    consecutive_losses = 0

    risk_config = RiskConfig(
        account_balance=balance,
        risk_per_trade=backtest_config.risk_per_trade,
        max_daily_loss=backtest_config.max_daily_loss,
        max_open_trades=backtest_config.max_open_trades,
        max_consecutive_losses=backtest_config.max_consecutive_losses,
        min_risk_reward=backtest_config.min_risk_reward,
        value_per_point=backtest_config.value_per_point,
    )

    i = backtest_config.warmup_candles

    while i < len(data) - 1:
        window = data.iloc[: i + 1]

        signal = generate_signal(window, strategy_config)
        risk_signal = from_trading_signal(signal)

        account_state = AccountState(
            current_daily_pnl=0.0,
            open_trades_count=0,
            consecutive_losses=consecutive_losses,
        )

        risk_config = RiskConfig(
            account_balance=balance,
            risk_per_trade=backtest_config.risk_per_trade,
            max_daily_loss=backtest_config.max_daily_loss,
            max_open_trades=backtest_config.max_open_trades,
            max_consecutive_losses=backtest_config.max_consecutive_losses,
            min_risk_reward=backtest_config.min_risk_reward,
            value_per_point=backtest_config.value_per_point,
        )

        decision = evaluate_signal_risk(risk_signal, risk_config, account_state)

        if not decision.approved:
            i += 1
            continue

        trade_result, exit_index = _simulate_trade_exit(
            data=data,
            entry_index=i,
            side=signal.side,
            entry_price=float(signal.entry_price),
            stop_loss=float(signal.stop_loss),
            take_profit=float(signal.take_profit),
            position_size=float(decision.position_size),
            value_per_point=backtest_config.value_per_point,
            commission_per_trade=backtest_config.commission_per_trade,
            slippage_points=backtest_config.slippage_points,
        )

        balance += trade_result["profit_loss"]

        if trade_result["profit_loss"] < 0:
            consecutive_losses += 1
        else:
            consecutive_losses = 0

        trade_result.update(
            {
                "symbol": signal.symbol,
                "timeframe": signal.timeframe,
                "risk_percent": decision.risk_percent,
                "risk_amount": decision.risk_amount,
                "risk_reward": signal.risk_reward,
                "confidence": signal.confidence,
                "reason_entry": signal.reason,
                "balance_after": balance,
            }
        )

        trades.append(trade_result)

        i = max(exit_index + 1, i + 1)

    trades_df = pd.DataFrame(trades)
    metrics = calculate_metrics(trades_df, backtest_config.initial_balance)

    return BacktestResult(
        trades=trades_df,
        metrics=metrics,
        final_balance=balance,
    )


def export_backtest_report(result: BacktestResult, output_dir: str | Path = "reports/backtests") -> tuple[Path, Path]:
    """Export trades and metrics to CSV files."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    trades_path = output_path / "trades.csv"
    metrics_path = output_path / "metrics.csv"

    result.trades.to_csv(trades_path, index=False)
    pd.DataFrame([metrics_to_dict(result.metrics)]).to_csv(metrics_path, index=False)

    return trades_path, metrics_path


def _simulate_trade_exit(
    data: pd.DataFrame,
    entry_index: int,
    side: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    position_size: float,
    value_per_point: float,
    commission_per_trade: float,
    slippage_points: float,
) -> tuple[dict, int]:
    """
    Simulate trade exit by scanning candles after entry.

    Conservative rule:
    if SL and TP are both touched in same candle, assume SL first.
    """
    entry_timestamp = data.index[entry_index]

    adjusted_entry = entry_price

    if side == "BUY":
        adjusted_entry += slippage_points
    elif side == "SELL":
        adjusted_entry -= slippage_points
    else:
        raise ValueError("side must be BUY or SELL")

    for j in range(entry_index + 1, len(data)):
        candle = data.iloc[j]
        timestamp_close = data.index[j]

        high = float(candle["High"])
        low = float(candle["Low"])

        if side == "BUY":
            hit_stop = low <= stop_loss
            hit_target = high >= take_profit

            if hit_stop:
                exit_price = stop_loss - slippage_points
                profit_loss = (exit_price - adjusted_entry) * position_size * value_per_point
                result = "LOSS"
                reason_exit = "Stop loss hit"
            elif hit_target:
                exit_price = take_profit - slippage_points
                profit_loss = (exit_price - adjusted_entry) * position_size * value_per_point
                result = "WIN"
                reason_exit = "Take profit hit"
            else:
                continue

        else:
            hit_stop = high >= stop_loss
            hit_target = low <= take_profit

            if hit_stop:
                exit_price = stop_loss + slippage_points
                profit_loss = (adjusted_entry - exit_price) * position_size * value_per_point
                result = "LOSS"
                reason_exit = "Stop loss hit"
            elif hit_target:
                exit_price = take_profit + slippage_points
                profit_loss = (adjusted_entry - exit_price) * position_size * value_per_point
                result = "WIN"
                reason_exit = "Take profit hit"
            else:
                continue

        profit_loss -= commission_per_trade

        return (
            {
                "timestamp_open": entry_timestamp,
                "timestamp_close": timestamp_close,
                "side": side,
                "entry_price": adjusted_entry,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "exit_price": exit_price,
                "position_size": position_size,
                "result": result,
                "profit_loss": profit_loss,
                "reason_exit": reason_exit,
            },
            j,
        )

    last_candle = data.iloc[-1]
    last_timestamp = data.index[-1]
    exit_price = float(last_candle["Close"])

    if side == "BUY":
        profit_loss = (exit_price - adjusted_entry) * position_size * value_per_point
    else:
        profit_loss = (adjusted_entry - exit_price) * position_size * value_per_point

    profit_loss -= commission_per_trade

    result = "WIN" if profit_loss > 0 else "LOSS" if profit_loss < 0 else "BREAKEVEN"

    return (
        {
            "timestamp_open": entry_timestamp,
            "timestamp_close": last_timestamp,
            "side": side,
            "entry_price": adjusted_entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "exit_price": exit_price,
            "position_size": position_size,
            "result": result,
            "profit_loss": profit_loss,
            "reason_exit": "End of data",
        },
        len(data) - 1,
    )


def _validate_ohlcv(df: pd.DataFrame) -> None:
    """Validate OHLCV columns."""
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"Missing required OHLCV columns: {missing}")

    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have a DatetimeIndex")
