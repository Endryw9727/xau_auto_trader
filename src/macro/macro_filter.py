"""
Macro trade filter.

This module intentionally keeps macro filtering conservative: it delegates
directional blocking to MacroEngine and never approves a trade by itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.macro.macro_engine import MacroAnalysisResult, MacroEngine


@dataclass(frozen=True)
class MacroFilterResult:
    """Result of applying macro context to a candidate side."""

    allowed: bool
    reason: str | None


class MacroFilter:
    """Small wrapper around MacroEngine directional blocking."""

    def __init__(self, engine: MacroEngine | None = None):
        self.engine = engine or MacroEngine()

    def check(self, result: MacroAnalysisResult, side: str) -> MacroFilterResult:
        blocked, reason = self.engine.should_block_side(result, side)
        if blocked:
            return MacroFilterResult(allowed=False, reason=reason)
        return MacroFilterResult(allowed=True, reason=None)
