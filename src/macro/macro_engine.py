"""
Macro engine: aggregates all macro indicators into a composite score.

Score range: -1.0 (strongly bearish for gold) to +1.0 (strongly bullish for gold).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from src.macro.correlation_analyzer import get_current_correlation, is_correlation_valid
from src.macro.dxy_fetcher import fetch_dxy, get_dxy_bias, get_dxy_current_value
from src.macro.macro_config import MacroConfig
from src.macro.macro_snapshot import MacroSnapshot
from src.macro.spx_fetcher import fetch_spx, get_spx_bias, get_spx_current_value
from src.macro.vix_fetcher import fetch_vix, get_vix_current_value, get_vix_level
from src.macro.yields_fetcher import fetch_us10y, get_yield_bias, get_yield_current_value

MacroScore = Literal["STRONG_BULLISH", "BULLISH", "NEUTRAL", "BEARISH", "STRONG_BEARISH"]

@dataclass(frozen=True)
class MacroAnalysisResult:
    """Result of macro analysis."""

    score: float  # -1.0 to +1.0
    score_label: MacroScore
    snapshot: MacroSnapshot
    dxy_correlation: float | None
    confidence: float  # 0.0 to 1.0
    block_trade: bool
    block_reason: str | None
    explanation: str

class MacroEngine:
    """Engine for macro fundamental analysis."""

    def __init__(self, config: MacroConfig = None):
        self.config = config or MacroConfig()

    def analyze(self, xau_df: pd.DataFrame | None = None) -> MacroAnalysisResult:
        """
        Run full macro analysis.

        Parameters:
        - xau_df: Optional XAU/USD DataFrame for correlation calculation

        Returns:
        - MacroAnalysisResult with score, snapshot, and trade blocking info
        """
        # DXY
        try:
            dxy_df = fetch_dxy()
            dxy_value = get_dxy_current_value(dxy_df)
            dxy_bias = get_dxy_bias(dxy_df)
        except Exception:
            dxy_value = None
            dxy_bias = "NEUTRAL"
            dxy_df = pd.DataFrame()

        # US10Y
        try:
            us10y_df = fetch_us10y()
            us10y_value = get_yield_current_value(us10y_df)
            us10y_bias = get_yield_bias(us10y_df)
        except Exception:
            us10y_value = None
            us10y_bias = "NEUTRAL"
            us10y_df = pd.DataFrame()

        # VIX
        try:
            vix_df = fetch_vix()
            vix_value = get_vix_current_value(vix_df)
            vix_level = get_vix_level(vix_df)
        except Exception:
            vix_value = None
            vix_level = "unknown"
            vix_df = pd.DataFrame()

        # SPX
        try:
            spx_df = fetch_spx()
            spx_value = get_spx_current_value(spx_df)
            spx_bias = get_spx_bias(spx_df)
        except Exception:
            spx_value = None
            spx_bias = "NEUTRAL"
            spx_df = pd.DataFrame()

        # Calculate correlations
        dxy_corr = None
        if xau_df is not None and not dxy_df.empty:
            dxy_corr = get_current_correlation(xau_df, dxy_df, self.config.correlation_window)

        # Score components (inverted for gold relationship)
        dxy_score = self._bias_to_score(dxy_bias, invert=True) * self.config.dxy_weight
        yield_score = self._bias_to_score(us10y_bias, invert=True) * self.config.us10y_weight
        vix_score = self._vix_to_score(vix_level) * self.config.vix_weight
        spx_score = self._bias_to_score(spx_bias, invert=True) * self.config.spx_weight

        total_score = dxy_score + yield_score + vix_score + spx_score
        total_score = max(-1.0, min(1.0, total_score))

        confidence = self._calculate_confidence(
            dxy_value, us10y_value, vix_value, spx_value, dxy_corr
        )

        block_trade = False
        block_reason = None

        score_label = self._score_to_label(total_score)

        snapshot = MacroSnapshot(
            dxy_value=dxy_value,
            dxy_trend=dxy_bias,
            us10y_value=us10y_value,
            us10y_trend=us10y_bias,
            vix_value=vix_value,
            vix_level=vix_level,
            spx_value=spx_value,
            spx_trend=spx_bias,
            timestamp=pd.Timestamp.now().isoformat(),
        )

        explanation = self._build_explanation(
            dxy_bias, us10y_bias, vix_level, spx_bias, total_score, dxy_corr
        )

        return MacroAnalysisResult(
            score=total_score,
            score_label=score_label,
            snapshot=snapshot,
            dxy_correlation=dxy_corr,
            confidence=confidence,
            block_trade=block_trade,
            block_reason=block_reason,
            explanation=explanation,
        )

    def _bias_to_score(self, bias: str, invert: bool = False) -> float:
        """Convert bias to score."""
        scores = {"BULLISH": 1.0, "BEARISH": -1.0, "NEUTRAL": 0.0}
        score = scores.get(bias, 0.0)
        return -score if invert else score

    def _vix_to_score(self, level: str) -> float:
        """Convert VIX level to gold sentiment score."""
        scores = {
            "extreme_fear": 1.0,
            "high_fear": 0.7,
            "elevated": 0.3,
            "normal": 0.0,
            "low": -0.2,
            "unknown": 0.0,
        }
        return scores.get(level, 0.0)

    def _calculate_confidence(
        self,
        dxy_value: float | None,
        us10y_value: float | None,
        vix_value: float | None,
        spx_value: float | None,
        dxy_corr: float | None,
    ) -> float:
        """Calculate confidence based on data availability."""
        available = sum(v is not None for v in [dxy_value, us10y_value, vix_value, spx_value])
        base_confidence = available / 4.0

        if dxy_corr is not None and abs(dxy_corr) >= 0.5:
            base_confidence = min(1.0, base_confidence + 0.2)

        return round(base_confidence, 2)

    def _score_to_label(self, score: float) -> MacroScore:
        """Convert numeric score to label."""
        if score >= 0.6:
            return "STRONG_BULLISH"
        elif score >= 0.2:
            return "BULLISH"
        elif score <= -0.6:
            return "STRONG_BEARISH"
        elif score <= -0.2:
            return "BEARISH"
        return "NEUTRAL"

    def _build_explanation(
        self,
        dxy_bias: str,
        us10y_bias: str,
        vix_level: str,
        spx_bias: str,
        score: float,
        dxy_corr: float | None,
    ) -> str:
        """Build human-readable explanation."""
        parts = [
            f"DXY: {dxy_bias} (gold inverse)",
            f"US10Y: {us10y_bias} (gold inverse)",
            f"VIX: {vix_level} (safe-haven proxy)",
            f"SPX: {spx_bias} (risk-on/off, gold inverse)",
        ]
        if dxy_corr is not None:
            parts.append(f"XAU/DXY correlation: {dxy_corr:.2f}")
        parts.append(f"Composite macro score: {score:.2f}")
        return " | ".join(parts)

    def should_block_side(self, result: MacroAnalysisResult, side: str) -> tuple[bool, str | None]:
        """Check if a trade side should be blocked based on macro analysis."""
        if not self.config.block_trade_against_macro:
            return False, None

        if abs(result.score) < self.config.macro_score_threshold:
            return False, None

        if result.score >= self.config.macro_score_threshold and side == "SELL":
            return True, f"Macro strongly bullish ({result.score:.2f}), blocking SELL"

        if result.score <= -self.config.macro_score_threshold and side == "BUY":
            return True, f"Macro strongly bearish ({result.score:.2f}), blocking BUY"

        return False, None
