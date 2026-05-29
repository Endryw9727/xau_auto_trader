"""Deterministic, auditable V51 reasoning layer.

This module intentionally makes no external LLM calls. It turns already
available V51, MTF, and execution telemetry into a repeatable decision summary
that can be logged or used as an additional safety veto when explicitly enabled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ReasoningBias = Literal["LONG_BIAS", "SHORT_BIAS", "MIXED", "NO_TRADE"]

TIMEFRAME_WEIGHTS = {
    "D1": 20.0,
    "H4": 20.0,
    "H1": 15.0,
    "M15": 15.0,
    "M5": 10.0,
    "M1": 10.0,
}
GOOD_SESSIONS = {"LONDON", "LONDON/US", "NEW YORK"}


@dataclass(frozen=True)
class TimeframeContext:
    """One timeframe's read-only context used by the reasoning engine."""

    timeframe: str
    trend_direction: str = "UNKNOWN"
    ema_alignment: str = "UNKNOWN"
    data_status: str = "UNKNOWN"
    used_in_bias: bool = True
    distance_from_support: float | None = None
    distance_from_resistance: float | None = None
    volatility_regime: str | None = None
    last_close: float | None = None


@dataclass(frozen=True)
class CandidateContext:
    """Selected V51 candidate and execution-quality telemetry."""

    side: Literal["BUY", "SELL"] | str
    score: float | None = None
    score_gap: float | None = None
    risk_reward: float | None = None
    session: str | None = None
    spread_points: float | None = None
    max_spread_points: float | None = None
    slippage_points: float | None = None
    max_slippage_points: float | None = None
    expected_entry_price: float | None = None


@dataclass(frozen=True)
class MacroContext:
    """Higher-level market/session context."""

    session: str | None = None
    market_open: bool = True
    volatility_regime: str | None = None


@dataclass(frozen=True)
class NewsRiskContext:
    """Optional news/event risk context."""

    risk_level: str = "UNKNOWN"
    high_impact_event: bool = False
    notes: str = ""


@dataclass(frozen=True)
class ReasoningInput:
    """Complete deterministic input for a V51 reasoning pass."""

    timeframes: tuple[TimeframeContext, ...] = ()
    candidate: CandidateContext | None = None
    macro: MacroContext = field(default_factory=MacroContext)
    news_risk: NewsRiskContext = field(default_factory=NewsRiskContext)
    mtf_final_bias: str | None = None
    mtf_context_status: str | None = None
    min_confidence_to_trade: float = 70.0
    min_trade_quality_score: float = 70.0


@dataclass(frozen=True)
class ReasoningDecision:
    """Auditable reasoning result."""

    final_bias: ReasoningBias
    confidence_score: float
    trade_quality_score: float
    allow_trade: bool
    veto_reasons: list[str]
    positive_factors: list[str]
    negative_factors: list[str]
    explanation: str


def evaluate_v51_reasoning(reasoning_input: ReasoningInput) -> ReasoningDecision:
    """Return a deterministic AI-style V51 decision."""
    positive: list[str] = []
    negative: list[str] = []
    veto: list[str] = []

    final_bias, confidence = _directional_bias(reasoning_input, positive, negative, veto)
    quality = _trade_quality_score(reasoning_input, final_bias, positive, negative, veto)

    candidate = reasoning_input.candidate
    if candidate is None:
        veto.append("no_v51_candidate")
    elif final_bias == "LONG_BIAS" and str(candidate.side).upper() != "BUY":
        veto.append("candidate_side_not_aligned_with_long_bias")
    elif final_bias == "SHORT_BIAS" and str(candidate.side).upper() != "SELL":
        veto.append("candidate_side_not_aligned_with_short_bias")

    if confidence < reasoning_input.min_confidence_to_trade:
        veto.append("ai_confidence_below_minimum")
    if quality < reasoning_input.min_trade_quality_score:
        veto.append("ai_trade_quality_below_minimum")
    if final_bias in {"MIXED", "NO_TRADE"}:
        veto.append("ai_final_bias_not_tradeable")

    veto = _dedupe(veto)
    allow_trade = not veto
    explanation = _build_explanation(final_bias, confidence, quality, allow_trade, veto, positive, negative)
    return ReasoningDecision(
        final_bias=final_bias,
        confidence_score=round(confidence, 2),
        trade_quality_score=round(quality, 2),
        allow_trade=allow_trade,
        veto_reasons=veto,
        positive_factors=_dedupe(positive),
        negative_factors=_dedupe(negative),
        explanation=explanation,
    )


def timeframe_contexts_from_records(records: list[dict[str, Any]]) -> tuple[TimeframeContext, ...]:
    """Build timeframe contexts from MTF summary CSV records."""
    contexts: list[TimeframeContext] = []
    for record in records:
        timeframe = str(record.get("timeframe", "")).upper()
        if not timeframe:
            continue
        contexts.append(
            TimeframeContext(
                timeframe=timeframe,
                trend_direction=str(record.get("trend_direction", "UNKNOWN")).upper(),
                ema_alignment=str(record.get("ema_alignment", "UNKNOWN")).upper(),
                data_status=str(record.get("data_status", record.get("status", "UNKNOWN"))).upper(),
                used_in_bias=_as_bool(record.get("used_in_bias", True)),
                distance_from_support=_float_or_none(record.get("distance_from_support")),
                distance_from_resistance=_float_or_none(record.get("distance_from_resistance")),
                volatility_regime=_text_or_none(record.get("volatility_regime")),
                last_close=_float_or_none(record.get("last_close")),
            )
        )
    return tuple(contexts)


def _directional_bias(
    reasoning_input: ReasoningInput,
    positive: list[str],
    negative: list[str],
    veto: list[str],
) -> tuple[ReasoningBias, float]:
    mtf_bias = str(reasoning_input.mtf_final_bias or "").upper()
    if mtf_bias in {"MIXED", "NO_TRADE_CONTEXT", "UNKNOWN"}:
        negative.append(f"MTF final bias is {mtf_bias or 'UNKNOWN'}")
        veto.append("mtf_context_not_directional")

    long_score = 0.0
    short_score = 0.0
    usable_weight = 0.0
    long_timeframes: list[str] = []
    short_timeframes: list[str] = []
    mixed_timeframes: list[str] = []

    for context in reasoning_input.timeframes:
        timeframe = context.timeframe.upper()
        weight = TIMEFRAME_WEIGHTS.get(timeframe, 5.0)
        if not context.used_in_bias or context.data_status not in {"OK", "EXCLUDED"}:
            negative.append(f"{timeframe} data not usable: {context.data_status}")
            continue
        direction = _context_direction(context)
        if direction == "BULL":
            long_score += weight
            usable_weight += weight
            long_timeframes.append(timeframe)
        elif direction == "BEAR":
            short_score += weight
            usable_weight += weight
            short_timeframes.append(timeframe)
        elif direction == "RANGE":
            usable_weight += weight * 0.5
            mixed_timeframes.append(timeframe)

    if long_timeframes:
        positive.append(f"Bullish alignment on {','.join(long_timeframes)}")
    if short_timeframes:
        positive.append(f"Bearish alignment on {','.join(short_timeframes)}")
    if mixed_timeframes:
        negative.append(f"Range or mixed structure on {','.join(mixed_timeframes)}")

    if usable_weight <= 0:
        veto.append("no_aligned_timeframe_context")
        return "NO_TRADE", 0.0

    difference = abs(long_score - short_score)
    confidence = 45.0 + min(difference / usable_weight, 1.0) * 55.0

    if long_score > 0 and short_score > 0 and difference <= 15.0:
        negative.append("Directional evidence is contradictory")
        return "MIXED", min(confidence, 55.0)
    if long_score > short_score:
        bias: ReasoningBias = "LONG_BIAS"
    elif short_score > long_score:
        bias = "SHORT_BIAS"
    else:
        bias = "MIXED"

    if mtf_bias == "LONG_BIAS" and bias == "SHORT_BIAS":
        negative.append("Reasoning bias conflicts with MTF LONG_BIAS")
        return "MIXED", min(confidence, 55.0)
    if mtf_bias == "SHORT_BIAS" and bias == "LONG_BIAS":
        negative.append("Reasoning bias conflicts with MTF SHORT_BIAS")
        return "MIXED", min(confidence, 55.0)

    return bias, confidence


def _trade_quality_score(
    reasoning_input: ReasoningInput,
    final_bias: ReasoningBias,
    positive: list[str],
    negative: list[str],
    veto: list[str],
) -> float:
    candidate = reasoning_input.candidate
    if candidate is None:
        negative.append("No V51 candidate is available")
        return 0.0

    quality = 0.0
    score = _bounded(_float_or_none(candidate.score) or 0.0, 0.0, 100.0)
    score_gap = max(_float_or_none(candidate.score_gap) or 0.0, 0.0)
    risk_reward = max(_float_or_none(candidate.risk_reward) or 0.0, 0.0)
    quality += score * 0.35
    quality += min(score_gap / 20.0, 1.0) * 15.0
    quality += min(risk_reward / 2.0, 1.0) * 20.0

    session = str(candidate.session or reasoning_input.macro.session or "").upper()
    if session in GOOD_SESSIONS:
        quality += 10.0
        positive.append(f"Session quality is acceptable: {session}")
    else:
        quality += 4.0
        negative.append(f"Session quality is weak or unknown: {session or 'UNKNOWN'}")

    quality += _cost_quality(candidate, positive, negative, veto)
    _support_resistance_notes(reasoning_input, final_bias, positive, negative)
    _volatility_notes(reasoning_input, positive, negative)
    _news_risk_notes(reasoning_input.news_risk, negative, veto)

    if score >= 75:
        positive.append(f"V51 candidate score is strong: {score:.1f}")
    elif score < 60:
        negative.append(f"V51 candidate score is weak: {score:.1f}")
    if risk_reward >= 1.2:
        positive.append(f"Risk/reward is acceptable: {risk_reward:.2f}")
    else:
        negative.append(f"Risk/reward is weak: {risk_reward:.2f}")

    return _bounded(quality, 0.0, 100.0)


def _cost_quality(
    candidate: CandidateContext,
    positive: list[str],
    negative: list[str],
    veto: list[str],
) -> float:
    cost_quality = 20.0
    spread = _float_or_none(candidate.spread_points)
    max_spread = _float_or_none(candidate.max_spread_points)
    slippage = _float_or_none(candidate.slippage_points)
    max_slippage = _float_or_none(candidate.max_slippage_points)

    if spread is not None and max_spread is not None and max_spread > 0:
        if spread > max_spread:
            negative.append(f"Spread exceeds limit: {spread:.1f}>{max_spread:.1f}")
            veto.append("spread_too_high")
        else:
            cost_quality -= min(spread / max_spread, 1.0) * 8.0
            positive.append(f"Spread is within limit: {spread:.1f}/{max_spread:.1f}")
    if slippage is not None and max_slippage is not None and max_slippage > 0:
        if slippage > max_slippage:
            negative.append(f"Slippage exceeds limit: {slippage:.1f}>{max_slippage:.1f}")
            veto.append("slippage_too_high")
        else:
            cost_quality -= min(slippage / max_slippage, 1.0) * 8.0
            positive.append(f"Slippage is within limit: {slippage:.1f}/{max_slippage:.1f}")
    return max(cost_quality, 0.0)


def _support_resistance_notes(
    reasoning_input: ReasoningInput,
    final_bias: ReasoningBias,
    positive: list[str],
    negative: list[str],
) -> None:
    setup = next((context for context in reasoning_input.timeframes if context.timeframe.upper() == "M15"), None)
    if setup is None:
        return
    support = setup.distance_from_support
    resistance = setup.distance_from_resistance
    if final_bias == "LONG_BIAS" and resistance is not None and support is not None:
        if resistance > support:
            positive.append("M15 has more room to resistance than distance to support")
        else:
            negative.append("M15 long setup has limited room to resistance")
    if final_bias == "SHORT_BIAS" and resistance is not None and support is not None:
        if support > resistance:
            positive.append("M15 has more room to support than distance to resistance")
        else:
            negative.append("M15 short setup has limited room to support")


def _volatility_notes(reasoning_input: ReasoningInput, positive: list[str], negative: list[str]) -> None:
    regimes = {
        str(context.volatility_regime).upper()
        for context in reasoning_input.timeframes
        if context.volatility_regime is not None
    }
    macro_regime = str(reasoning_input.macro.volatility_regime or "").upper()
    if macro_regime:
        regimes.add(macro_regime)
    if not regimes:
        return
    if {"EXTREME", "SPIKE"} & regimes:
        negative.append("Volatility regime is extreme")
    elif {"NORMAL", "EXPANDING", "HIGH"} & regimes:
        positive.append("Volatility regime is tradeable")


def _news_risk_notes(news: NewsRiskContext, negative: list[str], veto: list[str]) -> None:
    level = str(news.risk_level or "UNKNOWN").upper()
    if news.high_impact_event or level in {"HIGH", "EXTREME"}:
        negative.append(f"News risk is elevated: {level}")
        veto.append("news_risk_too_high")


def _context_direction(context: TimeframeContext) -> str:
    trend = str(context.trend_direction or "UNKNOWN").upper()
    alignment = str(context.ema_alignment or "UNKNOWN").upper()
    if trend in {"BULL", "BEAR", "RANGE"}:
        if alignment in {"BULL", "BEAR"} and alignment != trend and trend != "RANGE":
            return "RANGE"
        return trend
    if alignment in {"BULL", "BEAR"}:
        return alignment
    return "UNKNOWN"


def _build_explanation(
    final_bias: ReasoningBias,
    confidence: float,
    quality: float,
    allow_trade: bool,
    veto: list[str],
    positive: list[str],
    negative: list[str],
) -> str:
    decision = "allowed" if allow_trade else "blocked"
    first_veto = f" Primary veto: {veto[0]}." if veto else ""
    first_positive = f" Key positive: {positive[0]}." if positive else ""
    first_negative = f" Key negative: {negative[0]}." if negative else ""
    return (
        f"V51 reasoning {decision}: bias={final_bias}, confidence={confidence:.1f}, "
        f"quality={quality:.1f}.{first_veto}{first_positive}{first_negative}"
    )


def _bounded(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text_or_none(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value).upper()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
