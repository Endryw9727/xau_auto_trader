"""
Paper trading engine.

This module simulates forward testing on historical CSV data.
It processes candles one by one, similar to live market flow.

Flow:
- add indicators
- iterate candle by candle
- update open paper positions
- generate signal
- validate risk
- open simulated paper position
- export report
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.execution.paper_broker import PaperBroker
from src.risk.risk_manager import AccountState, RiskConfig, evaluate_signal_risk, from_trading_signal
from src.strategy.indicators import add_all_core_indicators
from src.strategy.rules import StrategyConfig
from src.strategy.signals import generate_signal
from src.journal.trade_journal import save_signal_to_db


@dataclass(frozen=True)
class PaperTradingConfig:
    """Paper trading configuration."""

    initial_balance: float = 1000.0
    risk_per_trade: float = 0.005
    max_risk_per_trade: float = 0.01
    max_daily_loss: float = 0.02
    max_open_trades: int = 1
    max_consecutive_losses: int = 3
    min_risk_reward: float = 2.0
    value_per_point: float = 1.0
    commission_per_trade: float = 0.0
    slippage_points: float = 0.0
    warmup_candles: int = 220


@dataclass(frozen=True)
class PaperTradingResult:
    """Paper trading result."""

    trades: pd.DataFrame
    final_balance: float
    total_trades: int
    wins: int
    losses: int
    breakeven: int
    net_profit: float


def run_paper_trading_on_data(
    df: pd.DataFrame,
    strategy_config: StrategyConfig | None = None,
    paper_config: PaperTradingConfig | None = None,
    db_path: str | Path = "data/database/trading.db",
    save_signals: bool = True,
) -> PaperTradingResult:
    """
    Run paper trading simulation candle by candle.

    This does not send real orders.
    """
    if strategy_config is None:
        strategy_config = StrategyConfig()

    if paper_config is None:
        paper_config = PaperTradingConfig()

    _validate_ohlcv(df)

    if len(df) <= paper_config.warmup_candles:
        raise ValueError("Not enough candles for paper trading warmup")

    data = add_all_core_indicators(df)

    broker = PaperBroker(
        initial_balance=paper_config.initial_balance,
        value_per_point=paper_config.value_per_point,
        commission_per_trade=paper_config.commission_per_trade,
        slippage_points=paper_config.slippage_points,
    )

    consecutive_losses = 0
    current_daily_pnl = 0.0
    current_day = None

    for i in range(paper_config.warmup_candles, len(data)):
        candle = data.iloc[i]
        timestamp = data.index[i]

        # Reset daily P&L when day changes
        if current_day != timestamp.date():
            current_day = timestamp.date()
            current_daily_pnl = 0.0

        closed_now = broker.update_with_candle(candle, timestamp)

        for closed_trade in closed_now:
            current_daily_pnl += closed_trade.profit_loss

            if closed_trade.profit_loss < 0:
                consecutive_losses += 1
            else:
                consecutive_losses = 0

        # Do not open new position if already at max open trades
        if len(broker.open_positions) >= paper_config.max_open_trades:
            continue

        window = data.iloc[: i + 1]
        signal = generate_signal(window, strategy_config)

        risk_signal = from_trading_signal(signal)

        risk_config = RiskConfig(
            account_balance=broker.balance,
            risk_per_trade=paper_config.risk_per_trade,
            max_risk_per_trade=paper_config.max_risk_per_trade,
            max_daily_loss=paper_config.max_daily_loss,
            max_open_trades=paper_config.max_open_trades,
            max_consecutive_losses=paper_config.max_consecutive_losses,
            min_risk_reward=paper_config.min_risk_reward,
            value_per_point=paper_config.value_per_point,
        )

        account_state = AccountState(
            current_daily_pnl=current_daily_pnl,
            open_trades_count=len(broker.open_positions),
            consecutive_losses=consecutive_losses,
        )

        decision = evaluate_signal_risk(risk_signal, risk_config, account_state)

        if save_signals:
            if signal.side in {"BUY", "SELL"}:
                save_signal_to_db(
                    signal,
                    db_path=db_path,
                    approved_by_risk_manager=decision.approved,
                    blocked_reason=None if decision.approved else decision.reason,
                )

        if not decision.approved:
            continue

        broker.open_position(
            symbol=signal.symbol,
            side=signal.side,
            entry_price=float(signal.entry_price),
            stop_loss=float(signal.stop_loss),
            take_profit=float(signal.take_profit),
            position_size=float(decision.position_size),
            opened_at=timestamp,
        )

    # Close remaining positions at final candle close
    final_candle = data.iloc[-1]
    final_timestamp = data.index[-1]
    broker.close_all_at_market(final_candle, final_timestamp, reason="End of paper data")

    trades = broker.get_closed_trades_dataframe()

    if trades.empty:
        return PaperTradingResult(
            trades=trades,
            final_balance=broker.balance,
            total_trades=0,
            wins=0,
            losses=0,
            breakeven=0,
            net_profit=broker.balance - paper_config.initial_balance,
        )

    wins = int((trades["profit_loss"] > 0).sum())
    losses = int((trades["profit_loss"] < 0).sum())
    breakeven = int((trades["profit_loss"] == 0).sum())
    net_profit = float(trades["profit_loss"].sum())

    return PaperTradingResult(
        trades=trades,
        final_balance=broker.balance,
        total_trades=len(trades),
        wins=wins,
        losses=losses,
        breakeven=breakeven,
        net_profit=net_profit,
    )


def export_paper_trading_report(
    result: PaperTradingResult,
    output_dir: str | Path = "reports/paper_trading",
) -> Path:
    """Export paper trading trades to CSV."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    trades_path = output_path / "paper_trades.csv"
    result.trades.to_csv(trades_path, index=False)

    return trades_path


def _validate_ohlcv(df: pd.DataFrame) -> None:
    """Validate OHLCV data."""
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"Missing required OHLCV columns: {missing}")

    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have a DatetimeIndex")
