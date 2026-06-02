"""
Futures contract manager for gold (GC) and other commodities.

Handles:
- Contract specifications
- Roll dates (front month to next month)
- Basis tracking (spot vs futures)
- Margin requirements
- Contango/Backwardation detection
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

@dataclass(frozen=True)
class FuturesContract:
    """Represents a futures contract."""

    symbol: str  # e.g., "GC"
    month_code: str  # F, G, H, J, K, M, N, Q, U, V, X, Z
    year: int
    expiry_date: str
    contract_size: float  # 100 oz for GC
    tick_size: float  # $0.10 for GC
    tick_value: float  # $10 per tick for GC
    initial_margin: float  # USD
    maintenance_margin: float  # USD

@dataclass(frozen=True)
class RollSchedule:
    """Contract roll schedule."""

    current_contract: FuturesContract
    next_contract: FuturesContract
    roll_window_start: str
    roll_window_end: str
    basis: float  # Current contract price - Next contract price
    roll_cost: float  # Cost to roll (positive = contango, negative = backwardation)


class FuturesCalendar:
    """Manages futures contract calendar and roll dates."""

    MONTH_CODES = ["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"]

    # Approximate expiry dates (simplified)
    EXPIRY_DAYS = {
        "GC": 28,  # Gold expires around 28th of prior month
        "SI": 28,  # Silver
        "CL": 20,  # Crude oil
    }

    @classmethod
    def get_contract(cls, symbol: str, target_date: datetime | None = None) -> FuturesContract:
        """Get the front-month contract for a symbol."""
        if target_date is None:
            target_date = datetime.now()

        # Find current front month
        month_idx = target_date.month - 1
        year = target_date.year

        # Adjust for expiry (contract expires before month end)
        expiry_day = cls.EXPIRY_DAYS.get(symbol, 28)
        if target_date.day > expiry_day:
            month_idx += 1
            if month_idx >= 12:
                month_idx = 0
                year += 1

        month_code = cls.MONTH_CODES[month_idx]

        # Simplified expiry calculation
        expiry_month = month_idx + 1
        expiry_year = year
        if expiry_month > 12:
            expiry_month = 1
            expiry_year += 1

        expiry = datetime(expiry_year, expiry_month, expiry_day)

        return FuturesContract(
            symbol=symbol,
            month_code=month_code,
            year=year,
            expiry_date=expiry.strftime("%Y-%m-%d"),
            contract_size=100.0 if symbol == "GC" else 5000.0 if symbol == "SI" else 1000.0,
            tick_size=0.10 if symbol == "GC" else 0.005 if symbol == "SI" else 0.01,
            tick_value=10.0 if symbol == "GC" else 25.0 if symbol == "SI" else 10.0,
            initial_margin=11000.0 if symbol == "GC" else 12000.0 if symbol == "SI" else 5000.0,
            maintenance_margin=10000.0 if symbol == "GC" else 11000.0 if symbol == "SI" else 4000.0,
        )

    @classmethod
    def get_next_contract(cls, symbol: str, current: FuturesContract) -> FuturesContract:
        """Get the next contract after current."""
        current_idx = cls.MONTH_CODES.index(current.month_code)
        next_idx = (current_idx + 1) % 12
        next_year = current.year + 1 if next_idx < current_idx else current.year

        month_code = cls.MONTH_CODES[next_idx]
        expiry_month = next_idx + 1
        expiry_year = next_year
        if expiry_month > 12:
            expiry_month = 1
            expiry_year += 1

        expiry_day = cls.EXPIRY_DAYS.get(symbol, 28)
        expiry = datetime(expiry_year, expiry_month, expiry_day)

        return FuturesContract(
            symbol=symbol,
            month_code=month_code,
            year=next_year,
            expiry_date=expiry.strftime("%Y-%m-%d"),
            contract_size=current.contract_size,
            tick_size=current.tick_size,
            tick_value=current.tick_value,
            initial_margin=current.initial_margin,
            maintenance_margin=current.maintenance_margin,
        )

    @classmethod
    def get_roll_schedule(cls, symbol: str, current_price: float, next_price: float) -> RollSchedule:
        """Get roll schedule with basis calculation."""
        current = cls.get_contract(symbol)
        next_contract = cls.get_next_contract(symbol, current)

        now = datetime.now()
        roll_start = now + timedelta(days=10)
        roll_end = datetime.strptime(current.expiry_date, "%Y-%m-%d") - timedelta(days=5)

        basis = current_price - next_price
        roll_cost = basis * current.contract_size  # Dollar cost per contract

        return RollSchedule(
            current_contract=current,
            next_contract=next_contract,
            roll_window_start=roll_start.strftime("%Y-%m-%d"),
            roll_window_end=roll_end.strftime("%Y-%m-%d"),
            basis=round(basis, 2),
            roll_cost=round(roll_cost, 2),
        )


class ContangoAnalyzer:
    """Analyzes futures curve for contango/backwardation."""

    @staticmethod
    def analyze_curve(prices: dict[str, float]) -> dict[str, Any]:
        """
        Analyze futures curve shape.

        Parameters:
        - prices: dict of {contract_month: price}

        Returns:
        - Analysis dict with contango/backwardation status
        """
        if len(prices) < 2:
            return {"status": "insufficient_data"}

        sorted_contracts = sorted(prices.items(), key=lambda x: x[0])
        front_price = sorted_contracts[0][1]

        spreads = []
        for i in range(1, len(sorted_contracts)):
            spread = sorted_contracts[i][1] - front_price
            spreads.append({
                "contract": sorted_contracts[i][0],
                "spread": round(spread, 2),
                "annualized_pct": round((spread / front_price) * (12 / i) * 100, 2),
            })

        avg_spread = sum(s["spread"] for s in spreads) / len(spreads)

        if avg_spread > 0:
            status = "contango"
            interpretation = "Future prices > spot. Negative roll yield. Consider short futures or spot."
        elif avg_spread < 0:
            status = "backwardation"
            interpretation = "Future prices < spot. Positive roll yield. Favorable for long futures."
        else:
            status = "flat"
            interpretation = "Flat curve. No roll yield advantage."

        return {
            "status": status,
            "front_price": front_price,
            "spreads": spreads,
            "average_spread": round(avg_spread, 2),
            "interpretation": interpretation,
            "recommendation": "long_futures" if status == "backwardation" else "short_futures_or_spot" if status == "contango" else "neutral",
        }

    @staticmethod
    def calculate_roll_yield(
        spot_price: float,
        futures_price: float,
        days_to_expiry: int,
    ) -> dict[str, float]:
        """Calculate implied roll yield."""
        if days_to_expiry <= 0 or spot_price <= 0:
            return {"roll_yield_annualized": 0.0}

        basis = futures_price - spot_price
        roll_yield = (basis / spot_price) * (365 / days_to_expiry) * 100

        return {
            "basis": round(basis, 2),
            "roll_yield_annualized_pct": round(roll_yield, 2),
            "days_to_expiry": days_to_expiry,
        }
