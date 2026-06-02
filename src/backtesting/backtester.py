"""
Backtester for XAU/USD strategy.

This module runs a historical backtest on OHLCV data.
It simulates trade execution using the strategy signals and risk manager.

It does not connect to any broker or execute real trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from src.analysis.session_analysis import classify_session
from src.risk.risk_manager import RiskConfig, RiskManager, TradeProposal
from src.strategy.rules import StrategyConfig
from src.strategy.signals import SignalSide, generate_signals

TradeOutcome = Literal["win", "loss", "breakeven"]

@dataclass(frozen=True)
class BacktestConfig:
    """Backtest configuration."""

    initial_balance: float = 1000.0
    risk_per_trade: float = 0.005
    max_risk_per_trade: float = 0.01
    max_daily_loss: float = 0.02
    max_open_trades: int = 2
    max_consecutive_losses: int = 3
    min_risk_reward: float = 2.0
    value_per_point: float = 1.0
    commission_per_trade: float = 0.0
    slippage_points: float = 0.0
    warmup_candles: int = 220
    rolling_window_candles: int | None = 500
    allowed_sessions: list[str] | None = None

@dataclass(frozen=True)
class BacktestResult:
    """Result of a backtest run."""

    trades: pd.DataFrame
    metrics: pd.DataFrame
    final_balance: float
    equity_curve: pd.DataFrame

def run_backtest(
    df: pd.DataFrame,
    strategy_config: StrategyConfig,
    backtest_config: BacktestConfig,
) -> BacktestResult:
    """
    Run a backtest on historical data.

    Parameters:
    - df: OHLCV DataFrame with Date index
    - strategy_config: strategy parameters
    - backtest_config: backtest parameters

    Returns:
    - BacktestResult with trades, metrics, and equity curve.
    """
    if df.empty:
        raise ValueError("DataFrame is empty")

    if len(df) < backtest_config.warmup_candles:
        raise ValueError(
            f"Not enough data for warmup ({backtest_config.warmup_candles} candles needed)"
        )

    signals_df = generate_signals(df, strategy_config)

    risk_config = RiskConfig(
        risk_per_trade=backtest_config.risk_per_trade,
        max_risk_per_trade=backtest_config.max_risk_per_trade,
        max_daily_loss=backtest_config.max_daily_loss,
        max_open_trades=backtest_config.max_open_trades,
        max_consecutive_losses=backtest_config.max_consecutive_losses,
        min_risk_reward=backtest_config.min_risk_reward,
        value_per_point=backtest_config.value_per_point,
    )

    risk_manager = RiskManager(risk_config, backtest_config.initial_balance)

    trades: list[dict] = []
    equity_curve: list[dict] = []
    balance = backtest_config.initial_balance

    for i in range(backtest_config.warmup_candles, len(signals_df)):
        row = signals_df.iloc[i]
        timestamp = signals_df.index[i]

        if backtest_config.allowed_sessions is not None:
            session = classify_session(timestamp)
            if session not in backtest_config.allowed_sessions:
                continue

        signal = row["signal"]

        if signal not in {"BUY", "SELL"}:
            equity_curve.append({
                "timestamp": timestamp,
                "balance": balance,
                "trades_open": len(risk_manager.open_trades),
            })
            continue

        entry = float(row["entry"])
        stop_loss = float(row["stop_loss"])
        take_profit = float(row["take_profit"])
        risk_reward = float(row["risk_reward"])

        proposal = TradeProposal(
            side=signal,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
            timestamp=timestamp,
        )

        check = risk_manager.can_open_trade(proposal)

        if not check.allowed:
            equity_curve.append({
                "timestamp": timestamp,
                "balance": balance,
                "trades_open": len(risk_manager.open_trades),
            })
            continue

        position_size = check.position_size

        if position_size is None:
            equity_curve.append({
                "timestamp": timestamp,
                "balance": balance,
                "trades_open": len(risk_manager.open_trades),
            })
            continue

        trade = {
            "id": f"trade_{len(trades)}",
            "timestamp": timestamp,
            "side": signal,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_reward": risk_reward,
            "units": position_size.units,
            "risk_amount": position_size.risk_amount,
        }

        risk_manager.register_trade(trade)
        trades.append(trade)

        future_prices = signals_df.iloc[i + 1:]

        if future_prices.empty:
            equity_curve.append({
                "timestamp": timestamp,
                "balance": balance,
                "trades_open": len(risk_manager.open_trades),
            })
            continue

        hit_stop = False
        hit_target = False
        exit_price = float(future_prices["Close"].iloc[-1])
        exit_time = future_prices.index[-1]

        for j in range(len(future_prices)):
            future_high = float(future_prices["High"].iloc[j])
            future_low = float(future_prices["Low"].iloc[j])

            if signal == "BUY":
                if future_low <= stop_loss:
                    hit_stop = True
                    exit_price = stop_loss
                    exit_time = future_prices.index[j]
                    break
                if future_high >= take_profit:
                    hit_target = True
                    exit_price = take_profit
                    exit_time = future_prices.index[j]
                    break
            else:
                if future_high >= stop_loss:
                    hit_stop = True
                    exit_price = stop_loss
                    exit_time = future_prices.index[j]
                    break
                if future_low <= take_profit:
                    hit_target = True
                    exit_price = take_profit
                    exit_time = future_prices.index[j]
                    break

        price_diff = exit_price - entry

        if signal == "SELL":
            price_diff = -price_diff

        outcome = price_diff * position_size.units * backtest_config.value_per_point
        outcome -= backtest_config.commission_per_trade

        if hit_stop:
            outcome_label: TradeOutcome = "loss"
        elif hit_target:
            outcome_label = "win"
        else:
            outcome_label = "breakeven"

        trade["exit_price"] = exit_price
        trade["exit_time"] = exit_time
        trade["outcome"] = outcome
        trade["outcome_label"] = outcome_label
        trade["hit_stop"] = hit_stop
        trade["hit_target"] = hit_target

        risk_manager.close_trade(trade["id"], outcome)
        balance = risk_manager.balance

        equity_curve.append({
            "timestamp": timestamp,
            "balance": balance,
            "trades_open": len(risk_manager.open_trades),
        })

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_curve)
    metrics_df = compute_metrics(trades_df, backtest_config.initial_balance)

    return BacktestResult(
        trades=trades_df,
        metrics=metrics_df,
        final_balance=balance,
        equity_curve=equity_df,
    )

def compute_metrics(trades_df: pd.DataFrame, initial_balance: float) -> pd.DataFrame:
    """
    Compute backtest performance metrics.
    """
    if trades_df.empty:
        return pd.DataFrame({
            "metric": ["total_trades", "wins", "losses", "breakeven", "win_rate", "profit_factor", "expectancy", "net_profit", "max_drawdown", "max_consecutive_wins", "max_consecutive_losses"],
            "value": [0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0],
        })

    total_trades = len(trades_df)
    wins = len(trades_df[trades_df["outcome_label"] == "win"])
    losses = len(trades_df[trades_df["outcome_label"] == "loss"])
    breakeven = len(trades_df[trades_df["outcome_label"] == "breakeven"])

    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

    total_profit = trades_df[trades_df["outcome"] > 0]["outcome"].sum()
    total_loss = abs(trades_df[trades_df["outcome"] < 0]["outcome"].sum())
    profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")

    net_profit = trades_df["outcome"].sum()
    expectancy = net_profit / total_trades if total_trades > 0 else 0.0

    cumulative = trades_df["outcome"].cumsum() + initial_balance
    running_max = cumulative.cummax()
    drawdown = running_max - cumulative
    max_drawdown = drawdown.max()

    outcomes = trades_df["outcome_label"].tolist()
    max_consecutive_wins = 0
    max_consecutive_losses = 0
    current_wins = 0
    current_losses = 0

    for outcome in outcomes:
        if outcome == "win":
            current_wins += 1
            current_losses = 0
            max_consecutive_wins = max(max_consecutive_wins, current_wins)
        elif outcome == "loss":
            current_losses += 1
            current_wins = 0
            max_consecutive_losses = max(max_consecutive_losses, current_losses)
        else:
            current_wins = 0
            current_losses = 0

    return pd.DataFrame({
        "metric": ["total_trades", "wins", "losses", "breakeven", "win_rate", "profit_factor", "expectancy", "net_profit", "max_drawdown", "max_consecutive_wins", "max_consecutive_losses"],
        "value": [total_trades, wins, losses, breakeven, win_rate, profit_factor, expectancy, net_profit, max_drawdown, max_consecutive_wins, max_consecutive_losses],
    })

def export_backtest_report(result: BacktestResult, report_dir: Path) -> tuple[Path, Path]:
    """
    Export backtest trades and metrics to CSV files.

    Returns:
    - (trades_path, metrics_path)
    """
    report_dir.mkdir(parents=True, exist_ok=True)

    trades_path = report_dir / "trades.csv"
    metrics_path = report_dir / "metrics.csv"

    result.trades.to_csv(trades_path, index=False)
    result.metrics.to_csv(metrics_path, index=False)

    return trades_path, metrics_path
