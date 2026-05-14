"""Input model for advisory AI reasoning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.macro.macro_snapshot import MacroSnapshot


@dataclass(frozen=True)
class AIDecisionContext:
    """Context passed to an advisory-only AI reasoning layer."""

    technical_score_long: float
    technical_score_short: float
    macro_snapshot: MacroSnapshot
    risk_state: dict[str, Any] = field(default_factory=dict)
    paper_mode: bool = True
    allow_live: bool = False
