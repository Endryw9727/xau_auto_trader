"""
Realtime-safe V50 proxy candidate.

This module freezes the proxy_balanced_combo rules as a research candidate.
It does not execute trades or use outcome fields to generate signals.
"""

from __future__ import annotations

from src.strategy_lab.v50_realtime_loss_proxy_sweep import (
    RealtimeLossProxyVariant,
    make_realtime_loss_proxy_signal_generator,
    validate_variant_no_leakage,
)


STRATEGY_NAME = "v50_proxy_balanced_candidate"
SOURCE_VARIANT_NAME = "proxy_balanced_combo"
WORST_HOURS = (11, 12, 20)

PROXY_BALANCED_VARIANT = RealtimeLossProxyVariant(
    variant_name=STRATEGY_NAME,
    min_score_gap=10.0,
    short_min_score=75.0,
    blocked_score_bucket_hours=(("score_70_74", WORST_HOURS),),
)

validate_variant_no_leakage(PROXY_BALANCED_VARIANT)

generate_signal = make_realtime_loss_proxy_signal_generator(PROXY_BALANCED_VARIANT)
