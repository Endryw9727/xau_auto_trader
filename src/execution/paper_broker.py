"""
Paper broker.

This module simulates trade execution without sending real orders.

It is used for:
- paper trading
- forward testing
- validating signal + risk manager behavior

No live trading happens here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import pandas as pd


PositionSide = Literal["BUY", "SELL"]
PositionStatus = Literal["OPEN", "CLOSED"]
TradeResult = Literal["WIN", "LOSS", "BREAKEVEN"]


@dataclass
class PaperPosition:
    """Simulated open position."""

    id: int
    symbol: str
    side: PositionSide
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    opened_at: datetime
    status: PositionStatus = "OPEN"


@dataclass
class ClosedPaperTrade:
    """Closed simulated trade."""

    position_id: int
    symbol: str
    side: PositionSide
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float
    position_size: float
    opened_at: datetime
    closed_at: datetime
    result: TradeResult
    profit_loss: float
    reason_exit: str


@dataclass
class PaperBroker:
    """
    Simple paper broker.

    Conservative rule:
    If SL and TP are both touched in the same candle, SL is assumed first.
    """

    initial_balance: float = 1000.0
    value_per_point: float = 1.0
    commission_per_trade: float = 0.0
    slippage_points: float = 0.0

    balance: float = field(init=False)
    next_position_id: int = field(default=1, init=False)
    open_positions: list[PaperPosition] = field(default_factory=list, init=False)
    closed_trades: list[ClosedPaperTrade] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        """Initialize broker balance."""
        if self.initial_balance <= 0:
            raise ValueError("initial_balance must be greater than 0")

        if self.value_per_point <= 0:
            raise ValueError("value_per_point must be greater than 0")

        self.balance = self.initial_balance

    def open_position(
        self,
        symbol: str,
        side: PositionSide,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        position_size: float,
        opened_at: datetime,
    ) -> PaperPosition:
        """Open a simulated position."""
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")

        if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
            raise ValueError("entry, stop loss and take profit must be greater than 0")

        if position_size <= 0:
            raise ValueError("position_size must be greater than 0")

        adjusted_entry = entry_price

        if side == "BUY":
            adjusted_entry += self.slippage_points
        else:
            adjusted_entry -= self.slippage_points

        position = PaperPosition(
            id=self.next_position_id,
            symbol=symbol,
            side=side,
            entry_price=adjusted_entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            opened_at=opened_at,
        )

        self.next_position_id += 1
        self.open_positions.append(position)

        return position

    def update_with_candle(self, candle: pd.Series, timestamp: datetime) -> list[ClosedPaperTrade]:
        """
        Update all open positions with a new candle.

        The candle must contain:
        High, Low, Close
        """
        _validate_candle(candle)

        closed_now: list[ClosedPaperTrade] = []

        for position in list(self.open_positions):
            closed_trade = self._check_position_exit(position, candle, timestamp)

            if closed_trade is not None:
                self.open_positions.remove(position)
                self.closed_trades.append(closed_trade)
                self.balance += closed_trade.profit_loss
                closed_now.append(closed_trade)

        return closed_now

    def close_all_at_market(self, candle: pd.Series, timestamp: datetime, reason: str = "Manual close") -> list[ClosedPaperTrade]:
        """Close all open positions at candle close price."""
        _validate_candle(candle)

        closed_now: list[ClosedPaperTrade] = []

        for position in list(self.open_positions):
            exit_price = float(candle["Close"])

            if position.side == "BUY":
                profit_loss = (exit_price - position.entry_price) * position.position_size * self.value_per_point
            else:
                profit_loss = (position.entry_price - exit_price) * position.position_size * self.value_per_point

            profit_loss -= self.commission_per_trade

            result = _result_from_pnl(profit_loss)

            closed_trade = ClosedPaperTrade(
                position_id=position.id,
                symbol=position.symbol,
                side=position.side,
                entry_price=position.entry_price,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                exit_price=exit_price,
                position_size=position.position_size,
                opened_at=position.opened_at,
                closed_at=timestamp,
                result=result,
                profit_loss=profit_loss,
                reason_exit=reason,
            )

            self.open_positions.remove(position)
            self.closed_trades.append(closed_trade)
            self.balance += profit_loss
            closed_now.append(closed_trade)

        return closed_now

    def get_closed_trades_dataframe(self) -> pd.DataFrame:
        """Return closed trades as DataFrame."""
        return pd.DataFrame([trade.__dict__ for trade in self.closed_trades])

    def _check_position_exit(
        self,
        position: PaperPosition,
        candle: pd.Series,
        timestamp: datetime,
    ) -> ClosedPaperTrade | None:
        """Check whether a position hit SL or TP."""
        high = float(candle["High"])
        low = float(candle["Low"])

        if position.side == "BUY":
            hit_stop = low <= position.stop_loss
            hit_target = high >= position.take_profit

            if hit_stop:
                exit_price = position.stop_loss - self.slippage_points
                profit_loss = (exit_price - position.entry_price) * position.position_size * self.value_per_point
                reason_exit = "Stop loss hit"
            elif hit_target:
                exit_price = position.take_profit - self.slippage_points
                profit_loss = (exit_price - position.entry_price) * position.position_size * self.value_per_point
                reason_exit = "Take profit hit"
            else:
                return None

        else:
            hit_stop = high >= position.stop_loss
            hit_target = low <= position.take_profit

            if hit_stop:
                exit_price = position.stop_loss + self.slippage_points
                profit_loss = (position.entry_price - exit_price) * position.position_size * self.value_per_point
                reason_exit = "Stop loss hit"
            elif hit_target:
                exit_price = position.take_profit + self.slippage_points
                profit_loss = (position.entry_price - exit_price) * position.position_size * self.value_per_point
                reason_exit = "Take profit hit"
            else:
                return None

        profit_loss -= self.commission_per_trade
        result = _result_from_pnl(profit_loss)

        return ClosedPaperTrade(
            position_id=position.id,
            symbol=position.symbol,
            side=position.side,
            entry_price=position.entry_price,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            exit_price=exit_price,
            position_size=position.position_size,
            opened_at=position.opened_at,
            closed_at=timestamp,
            result=result,
            profit_loss=profit_loss,
            reason_exit=reason_exit,
        )


def _validate_candle(candle: pd.Series) -> None:
    """Validate candle data."""
    required = ["High", "Low", "Close"]
    missing = [column for column in required if column not in candle.index]

    if missing:
        raise ValueError(f"Missing candle columns: {missing}")


def _result_from_pnl(profit_loss: float) -> TradeResult:
    """Convert P&L to result label."""
    if profit_loss > 0:
        return "WIN"

    if profit_loss < 0:
        return "LOSS"

    return "BREAKEVEN"
