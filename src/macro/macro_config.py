"""
Macro configuration dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class MacroConfig:
    """Configuration for macro fundamental analysis."""

    enabled: bool = True
    dxy_weight: float = 0.35
    us10y_weight: float = 0.25
    vix_weight: float = 0.20
    spx_weight: float = 0.20
    correlation_window: int = 50
    dxy_symbol: str = "DX-Y.NYB"
    us10y_symbol: str = "^TNX"
    vix_symbol: str = "^VIX"
    spx_symbol: str = "^GSPC"
    min_correlation_confidence: float = 0.65
    block_trade_against_macro: bool = True
    macro_score_threshold: float = 0.30
