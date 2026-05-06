"""
Backtesting metrics.

This module calculates performance metrics from simulated trades.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class BacktestMetrics:
    """Backtest performance summary."""

    total_trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    net_profit: float
    profit_factor: float
    average_win: float
    average_loss: float
    expectancy: float
    max_drawdown: float
    max_consecutive_wins: int
    max_consecutive_losses: int


def calculate_metrics(trades: pd.DataFrame, initial_balance: float) -> BacktestMetrics:
    """
    Calculate performance metrics from a trades DataFrame.

    Required column:
    profit_loss
    """
    if initial_balance <= 0:
        raise ValueError("initial_balance must be greater than 0")

    if trades.empty:
        return BacktestMetrics(
            total_trades=0,
            wins=0,
            losses=0,
            breakeven=0,
            win_rate=0.0,
            net_profit=0.0,
            profit_factor=0.0,
            average_win=0.0,
            average_loss=0.0,
            expectancy=0.0,
            max_drawdown=0.0,
            max_consecutive_wins=0,
            max_consecutive_losses=0,
        )

    if "profit_loss" not in trades.columns:
        raise ValueError("trades DataFrame must contain profit_loss column")

    pnl = trades["profit_loss"].fillna(0.0)

    wins_series = pnl[pnl > 0]
    losses_series = pnl[pnl < 0]
    breakeven_series = pnl[pnl == 0]

    total_trades = len(pnl)
    wins = len(wins_series)
    losses = len(losses_series)
    breakeven = len(breakeven_series)

    gross_profit = wins_series.sum()
    gross_loss = abs(losses_series.sum())

    win_rate = wins / total_trades * 100 if total_trades > 0 else 0.0
    net_profit = pnl.sum()
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

    average_win = wins_series.mean() if wins > 0 else 0.0
    average_loss = losses_series.mean() if losses > 0 else 0.0
    expectancy = pnl.mean() if total_trades > 0 else 0.0

    equity_curve = initial_balance + pnl.cumsum()
    max_drawdown = calculate_max_drawdown(equity_curve)

    max_consecutive_wins = calculate_max_consecutive(pnl, positive=True)
    max_consecutive_losses = calculate_max_consecutive(pnl, positive=False)

    return BacktestMetrics(
        total_trades=total_trades,
        wins=wins,
        losses=losses,
        breakeven=breakeven,
        win_rate=win_rate,
        net_profit=net_profit,
        profit_factor=profit_factor,
        average_win=average_win,
        average_loss=average_loss,
        expectancy=expectancy,
        max_drawdown=max_drawdown,
        max_consecutive_wins=max_consecutive_wins,
        max_consecutive_losses=max_consecutive_losses,
    )


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """
    Calculate maximum drawdown in money amount.

    Returns positive drawdown value.
    """
    if equity_curve.empty:
        return 0.0

    running_max = equity_curve.cummax()
    drawdown = equity_curve - running_max

    return abs(float(drawdown.min()))


def calculate_max_consecutive(pnl: pd.Series, positive: bool) -> int:
    """Calculate maximum consecutive wins or losses."""
    max_count = 0
    current_count = 0

    for value in pnl:
        if positive:
            condition = value > 0
        else:
            condition = value < 0

        if condition:
            current_count += 1
            max_count = max(max_count, current_count)
        else:
            current_count = 0

    return max_count


def metrics_to_dict(metrics: BacktestMetrics) -> dict:
    """Convert BacktestMetrics to dict."""
    return {
        "total_trades": metrics.total_trades,
        "wins": metrics.wins,
        "losses": metrics.losses,
        "breakeven": metrics.breakeven,
        "win_rate": metrics.win_rate,
        "net_profit": metrics.net_profit,
        "profit_factor": metrics.profit_factor,
        "average_win": metrics.average_win,
        "average_loss": metrics.average_loss,
        "expectancy": metrics.expectancy,
        "max_drawdown": metrics.max_drawdown,
        "max_consecutive_wins": metrics.max_consecutive_wins,
        "max_consecutive_losses": metrics.max_consecutive_losses,
    }
