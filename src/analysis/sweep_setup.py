"""
Liquidity-sweep + reclaim setup (read-only research).

Operationalises the project's central thesis — Asia builds a range (liquidity),
a later session sweeps beyond it (manipulation), price reclaims the range and
reverses — as a *tradable, point-in-time* setup with a structural stop and a
designed reward:risk:

- Reference: the Asia session high/low of the day (known once Asia closes).
- Sweep + reclaim: during a later session (London/NY), price trades beyond the
  Asia extreme, then a candle CLOSES back inside the range. That close is the
  entry, faded against the sweep (short after an upside sweep, long after a
  downside sweep).
- Stop: just beyond the swept extreme (structural). Target: a designed multiple
  of that risk. Outcome is first-touch over the rest of the day.

No lookahead: the Asia level precedes the sweep window; detection walks candles in
order; the outcome only inspects candles strictly after entry. Pure research: no
IO, no execution, no orders. Outputs per-trade R-multiples.
"""

from __future__ import annotations

import pandas as pd

from src.analysis.session_structure import add_session_columns
from src.analysis.session_edge_lab import _ensure_ohlc
from src.analysis.setup_simulation import simulate_barrier

_SWEEP_SESSIONS = ("LONDON", "LONDON/US", "NEW YORK")


def _first_sweep_reclaim(window: pd.DataFrame, asia_high: float, asia_low: float):
    """First upside and downside sweep+reclaim signals in a session window.

    Returns a dict side -> (entry_time, entry_price, stop_price). ``entry`` is the
    close of the candle that reclaims the Asia range after sweeping beyond it.
    """
    signals: dict[str, tuple] = {}
    swept_up_high = None   # running extreme once price trades above asia_high
    swept_dn_low = None    # running extreme once price trades below asia_low
    for time, candle in window.iterrows():
        high = float(candle["High"])
        low = float(candle["Low"])
        close = float(candle["Close"])
        # Upside sweep -> short on reclaim back below asia_high.
        if high > asia_high:
            swept_up_high = high if swept_up_high is None else max(swept_up_high, high)
        if "SHORT" not in signals and swept_up_high is not None and close < asia_high:
            signals["SHORT"] = (time, close, swept_up_high)
        # Downside sweep -> long on reclaim back above asia_low.
        if low < asia_low:
            swept_dn_low = low if swept_dn_low is None else min(swept_dn_low, low)
        if "LONG" not in signals and swept_dn_low is not None and close > asia_low:
            signals["LONG"] = (time, close, swept_dn_low)
    return signals


def asia_sweep_trades(
    market_data: pd.DataFrame,
    symbol: str,
    *,
    reward_risk: float = 2.0,
    stop_buffer_pct: float = 0.02,
    cost_r: float = 0.0,
) -> dict[str, pd.Series]:
    """Per-trade R-multiples for the Asia-sweep+reclaim setup.

    Keys are ``"<symbol>/ASIA_SWEEP/<side>"``. One trade per side per day (the
    first clean sweep+reclaim), entered at the reclaim close, stopped beyond the
    swept extreme (plus ``stop_buffer_pct``), targeted at ``reward_risk`` times the
    risk, simulated first-touch over the rest of the day.
    """
    if reward_risk <= 0:
        raise ValueError("reward_risk must be positive")
    data = _ensure_ohlc(market_data)
    if data.empty:
        return {}
    data = add_session_columns(data)
    data["day"] = data.index.normalize()

    out: dict[str, list[tuple[pd.Timestamp, float]]] = {}
    for day, group in data.groupby("day", sort=True):
        group = group.sort_index()
        asia = group[group["session"] == "ASIA"]
        window = group[group["session"].isin(_SWEEP_SESSIONS)]
        if asia.empty or window.empty:
            continue
        asia_high = float(asia["High"].max())
        asia_low = float(asia["Low"].min())
        if asia_high <= asia_low:
            continue

        signals = _first_sweep_reclaim(window, asia_high, asia_low)
        for side, (entry_time, entry_price, extreme) in signals.items():
            future = group[group.index > entry_time]
            if future.empty or entry_price <= 0:
                continue
            if side == "SHORT":
                stop = extreme * (1.0 + stop_buffer_pct / 100.0)
                risk = stop - entry_price
                target = entry_price - risk * reward_risk
            else:
                stop = extreme * (1.0 - stop_buffer_pct / 100.0)
                risk = entry_price - stop
                target = entry_price + risk * reward_risk
            if risk <= 0:
                continue
            outcome = simulate_barrier(
                future["High"].to_numpy(), future["Low"].to_numpy(), future["Close"].to_numpy(),
                entry_price=entry_price, stop_price=stop, target_price=target, side=side,
            )
            key = f"{symbol}/ASIA_SWEEP/{side}"
            out.setdefault(key, []).append((pd.Timestamp(day), outcome.r_multiple - cost_r))

    return {
        key: pd.Series([r for _, r in rows], index=pd.DatetimeIndex([d for d, _ in rows]))
        for key, rows in out.items()
    }
