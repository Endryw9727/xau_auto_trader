"""V2-inspired report-only AI explanation for shadow diagnostics."""

from __future__ import annotations

from dataclasses import dataclass

from src.v2_shadow.macro import ShadowMacroSnapshot
from src.v2_shadow.news import ShadowNewsWarning
from src.v2_shadow.smart_money import ShadowSMCReport


@dataclass(frozen=True)
class ShadowAIReasoning:
    """Composite shadow explanation. It cannot execute or block trades."""

    recommendation: str
    confidence: float
    score: float
    positive_factors: tuple[str, ...]
    warning_factors: tuple[str, ...]
    explanation: str
    report_only: bool = True
    can_execute: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "recommendation": self.recommendation,
            "confidence": self.confidence,
            "score": self.score,
            "positive_factors": list(self.positive_factors),
            "warning_factors": list(self.warning_factors),
            "explanation": self.explanation,
            "report_only": self.report_only,
            "can_execute": self.can_execute,
        }


def compose_shadow_reasoning(
    *,
    candidate: dict[str, object] | None,
    indicator_snapshot: dict[str, float | None],
    smc: ShadowSMCReport,
    macro: ShadowMacroSnapshot,
    news: ShadowNewsWarning,
) -> ShadowAIReasoning:
    """Compose deterministic shadow reasoning from diagnostic inputs."""
    positives: list[str] = []
    warnings: list[str] = []
    score = 0.35

    if candidate:
        score += 0.2
        positives.append(f"V1 candidate/log context available: {candidate.get('signal_id') or 'unnamed'}")
        side = str(candidate.get("side") or "").upper()
    else:
        warnings.append("No live V1 candidate found; shadow report is diagnostic only.")
        side = ""

    rsi = indicator_snapshot.get("v2_shadow_rsi_14")
    if rsi is not None:
        positives.append(f"V2 shadow RSI available: {rsi:.1f}")
        score += 0.05
    atr = indicator_snapshot.get("v2_shadow_atr_14")
    if atr is not None:
        positives.append(f"V2 shadow ATR available: {atr:.2f}")
        score += 0.05

    if smc.bias != "NEUTRAL":
        positives.append(f"SMC overlay bias={smc.bias}")
        if (side == "BUY" and smc.bias == "BULLISH") or (side == "SELL" and smc.bias == "BEARISH"):
            score += 0.1
        else:
            warnings.append("SMC overlay is not aligned with V1 candidate side.")
    else:
        warnings.append("SMC overlay is neutral.")

    if macro.bias in {"BULLISH", "BEARISH"}:
        positives.append(f"Macro proxy bias={macro.bias}")
        score += 0.05 * macro.confidence
    else:
        warnings.append("Macro proxy is unavailable or neutral.")

    if news.risk_level == "HIGH":
        warnings.append("News warning layer reports HIGH risk, warning-only.")
        score -= 0.05
    elif news.risk_level != "UNKNOWN":
        positives.append(f"News warning layer risk={news.risk_level}")

    score = round(max(0.0, min(1.0, score)), 3)
    confidence = round(min(0.9, 0.25 + score * 0.7), 3)
    if not candidate:
        recommendation = "NO_CANDIDATE"
    elif score >= 0.65:
        recommendation = "WATCH_SUPPORTIVE"
    elif score >= 0.45:
        recommendation = "WATCH_MIXED"
    else:
        recommendation = "WATCH_WEAK"

    explanation = (
        f"V2 shadow reasoning recommendation={recommendation}, score={score:.3f}, "
        "report-only; no broker, execution, or live filter is invoked."
    )
    return ShadowAIReasoning(
        recommendation,
        confidence,
        score,
        tuple(positives),
        tuple(warnings),
        explanation,
    )
