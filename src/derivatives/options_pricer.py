"""
Options pricing and Greeks calculator for XAU/USD options.

Supports:
- Black-Scholes pricing for gold options
- Greeks: Delta, Gamma, Theta, Vega, Rho
- Implied volatility estimation
- Option strategy builder (straddle, strangle, spread)

Note: Gold options are typically on COMEX GC futures.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from scipy import stats

OptionType = Literal["CALL", "PUT"]

@dataclass(frozen=True)
class OptionGreeks:
    """Greeks for an option."""

    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float

@dataclass(frozen=True)
class OptionPrice:
    """Option pricing result."""

    price: float
    intrinsic_value: float
    time_value: float
    greeks: OptionGreeks
    break_even: float
    max_profit: float | None
    max_loss: float

@dataclass(frozen=True)
class OptionContract:
    """Represents an option contract specification."""

    underlying: str  # e.g., "GC" for gold futures
    strike: float
    expiry_days: int
    option_type: OptionType
    contract_size: float = 100.0  # 100 troy ounces for GC
    tick_size: float = 0.10


class BlackScholesPricer:
    """Black-Scholes option pricer for commodities."""

    @staticmethod
    def price(
        spot: float,
        strike: float,
        time_to_expiry: float,  # in years
        risk_free_rate: float,
        volatility: float,
        option_type: OptionType,
        dividend_yield: float = 0.0,
    ) -> OptionPrice:
        """
        Price an option using Black-Scholes.

        Parameters:
        - spot: current underlying price
        - strike: option strike price
        - time_to_expiry: time to expiration in years
        - risk_free_rate: annual risk-free rate (e.g., 0.05 for 5%)
        - volatility: annual implied volatility (e.g., 0.20 for 20%)
        - option_type: CALL or PUT
        - dividend_yield: continuous dividend yield (0 for gold)

        Returns:
        - OptionPrice with price, greeks, and risk metrics
        """
        if time_to_expiry <= 0:
            # At expiry
            if option_type == "CALL":
                price = max(0, spot - strike)
            else:
                price = max(0, strike - spot)

            return OptionPrice(
                price=price,
                intrinsic_value=price,
                time_value=0.0,
                greeks=OptionGreeks(0.0, 0.0, 0.0, 0.0, 0.0),
                break_even=strike + price if option_type == "CALL" else strike - price,
                max_profit=float("inf") if option_type == "CALL" else float("inf"),
                max_loss=price,
            )

        d1 = (math.log(spot / strike) + (risk_free_rate - dividend_yield + 0.5 * volatility ** 2) * time_to_expiry) / (volatility * math.sqrt(time_to_expiry))
        d2 = d1 - volatility * math.sqrt(time_to_expiry)

        nd1 = stats.norm.cdf(d1)
        nd2 = stats.norm.cdf(d2)
        n_d1 = stats.norm.cdf(-d1)
        n_d2 = stats.norm.cdf(-d2)
        pdf_d1 = stats.norm.pdf(d1)

        if option_type == "CALL":
            price = spot * math.exp(-dividend_yield * time_to_expiry) * nd1 - strike * math.exp(-risk_free_rate * time_to_expiry) * nd2
            delta = math.exp(-dividend_yield * time_to_expiry) * nd1
            intrinsic = max(0, spot - strike)
            break_even = strike + price
            max_profit = float("inf")
        else:
            price = strike * math.exp(-risk_free_rate * time_to_expiry) * n_d2 - spot * math.exp(-dividend_yield * time_to_expiry) * n_d1
            delta = -math.exp(-dividend_yield * time_to_expiry) * n_d1
            intrinsic = max(0, strike - spot)
            break_even = strike - price
            max_profit = strike - price  # Max if spot goes to 0

        gamma = math.exp(-dividend_yield * time_to_expiry) * pdf_d1 / (spot * volatility * math.sqrt(time_to_expiry))
        theta = -(spot * math.exp(-dividend_yield * time_to_expiry) * pdf_d1 * volatility) / (2 * math.sqrt(time_to_expiry))
        theta += risk_free_rate * strike * math.exp(-risk_free_rate * time_to_expiry) * (nd2 if option_type == "CALL" else -n_d2)
        theta -= dividend_yield * spot * math.exp(-dividend_yield * time_to_expiry) * (nd1 if option_type == "CALL" else -n_d1)
        vega = spot * math.exp(-dividend_yield * time_to_expiry) * pdf_d1 * math.sqrt(time_to_expiry)
        rho = strike * time_to_expiry * math.exp(-risk_free_rate * time_to_expiry) * (nd2 if option_type == "CALL" else -n_d2)

        return OptionPrice(
            price=round(price, 2),
            intrinsic_value=round(intrinsic, 2),
            time_value=round(price - intrinsic, 2),
            greeks=OptionGreeks(
                delta=round(delta, 4),
                gamma=round(gamma, 6),
                theta=round(theta / 365, 4),  # Daily theta
                vega=round(vega / 100, 4),  # Per 1% vol change
                rho=round(rho / 100, 4),  # Per 1% rate change
            ),
            break_even=round(break_even, 2),
            max_profit=max_profit,
            max_loss=round(price, 2),
        )

    @staticmethod
    def implied_volatility(
        market_price: float,
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        option_type: OptionType,
        precision: float = 0.0001,
        max_iterations: int = 100,
    ) -> float | None:
        """
        Calculate implied volatility using Newton-Raphson method.

        Returns None if convergence fails.
        """
        vol = 0.20  # Initial guess

        for _ in range(max_iterations):
            price = BlackScholesPricer.price(spot, strike, time_to_expiry, risk_free_rate, vol, option_type)
            diff = price.price - market_price

            if abs(diff) < precision:
                return round(vol, 4)

            # Vega is sensitivity to vol
            vega = price.greeks.vega * 100  # Convert back from per 1%
            if abs(vega) < 1e-10:
                return None

            vol -= diff / vega
            vol = max(0.001, min(2.0, vol))  # Bound volatility

        return None


class OptionStrategyBuilder:
    """Builder for multi-leg option strategies."""

    @staticmethod
    def straddle(
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        volatility: float,
    ) -> dict[str, Any]:
        """Long straddle: buy call + buy put at same strike."""
        call = BlackScholesPricer.price(spot, strike, time_to_expiry, risk_free_rate, volatility, "CALL")
        put = BlackScholesPricer.price(spot, strike, time_to_expiry, risk_free_rate, volatility, "PUT")

        total_cost = call.price + put.price

        return {
            "strategy": "Long Straddle",
            "legs": [
                {"type": "CALL", "strike": strike, "price": call.price, "delta": call.greeks.delta},
                {"type": "PUT", "strike": strike, "price": put.price, "delta": put.greeks.delta},
            ],
            "total_cost": round(total_cost, 2),
            "max_loss": round(total_cost, 2),
            "max_profit": "Unlimited",
            "break_even_up": round(strike + total_cost, 2),
            "break_even_down": round(strike - total_cost, 2),
            "net_delta": round(call.greeks.delta + put.greeks.delta, 4),
            "net_gamma": round(call.greeks.gamma + put.greeks.gamma, 6),
            "net_theta": round(call.greeks.theta + put.greeks.theta, 4),
            "net_vega": round(call.greeks.vega + put.greeks.vega, 4),
        }

    @staticmethod
    def strangle(
        spot: float,
        call_strike: float,
        put_strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        volatility: float,
    ) -> dict[str, Any]:
        """Long strangle: buy OTM call + buy OTM put."""
        call = BlackScholesPricer.price(spot, call_strike, time_to_expiry, risk_free_rate, volatility, "CALL")
        put = BlackScholesPricer.price(spot, put_strike, time_to_expiry, risk_free_rate, volatility, "PUT")

        total_cost = call.price + put.price

        return {
            "strategy": "Long Strangle",
            "legs": [
                {"type": "CALL", "strike": call_strike, "price": call.price, "delta": call.greeks.delta},
                {"type": "PUT", "strike": put_strike, "price": put.price, "delta": put.greeks.delta},
            ],
            "total_cost": round(total_cost, 2),
            "max_loss": round(total_cost, 2),
            "max_profit": "Unlimited",
            "break_even_up": round(call_strike + total_cost, 2),
            "break_even_down": round(put_strike - total_cost, 2),
            "net_delta": round(call.greeks.delta + put.greeks.delta, 4),
        }

    @staticmethod
    def bull_call_spread(
        spot: float,
        lower_strike: float,
        upper_strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        volatility: float,
    ) -> dict[str, Any]:
        """Bull call spread: buy lower strike call, sell higher strike call."""
        long_call = BlackScholesPricer.price(spot, lower_strike, time_to_expiry, risk_free_rate, volatility, "CALL")
        short_call = BlackScholesPricer.price(spot, upper_strike, time_to_expiry, risk_free_rate, volatility, "CALL")

        net_cost = long_call.price - short_call.price
        max_profit = (upper_strike - lower_strike) - net_cost

        return {
            "strategy": "Bull Call Spread",
            "legs": [
                {"type": "BUY_CALL", "strike": lower_strike, "price": long_call.price},
                {"type": "SELL_CALL", "strike": upper_strike, "price": short_call.price},
            ],
            "net_cost": round(net_cost, 2),
            "max_loss": round(net_cost, 2),
            "max_profit": round(max_profit, 2),
            "break_even": round(lower_strike + net_cost, 2),
        }
