"""
Macro snapshot model.

This module defines the data structure for macroeconomic data snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MacroBias = Literal["BULLISH", "BEARISH", "NEUTRAL"]

@dataclass(frozen=True)
class MacroSnapshot:
    """Snapshot of macroeconomic indicators."""

    dxy_value: float | None = None
    dxy_trend: MacroBias = "NEUTRAL"
    us10y_value: float | None = None
    us10y_trend: MacroBias = "NEUTRAL"
    vix_value: float | None = None
    vix_level: str = "normal"
    spx_value: float | None = None
    spx_trend: MacroBias = "NEUTRAL"
    timestamp: str = ""

    def __post_init__(self):
        valid_trends = {"BULLISH", "BEARISH", "NEUTRAL"}
        if self.dxy_trend not in valid_trends:
            raise ValueError(f"Invalid dxy_trend: {self.dxy_trend}")
        if self.us10y_trend not in valid_trends:
            raise ValueError(f"Invalid us10y_trend: {self.us10y_trend}")
        if self.spx_trend not in valid_trends:
            raise ValueError(f"Invalid spx_trend: {self.spx_trend}")
