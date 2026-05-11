from dataclasses import fields
from pathlib import Path
import inspect

import pytest

from src.strategy_lab.v50_fast_loss_proxies import validate_no_leakage_columns
from src.strategy_lab.v50_realtime_loss_proxy_sweep import (
    ENTRY_FILTER_COLUMNS,
    RealtimeLossProxyVariant,
    _side_allowed,
    _side_setup_ok,
    build_realtime_loss_proxy_variants,
    validate_variant_no_leakage,
)


FORBIDDEN_SIGNAL_FILTER_TERMS = ("bars_in_trade", "pnl", "exit_time", "trade_result")


def test_leakage_guard_rejects_outcome_columns():
    for column in ["bars_in_trade", "pnl", "exit_time", "trade_result", "result", "profit_loss", "max_drawdown"]:
        with pytest.raises(ValueError):
            validate_no_leakage_columns([column])


def test_realtime_entry_filter_columns_are_entry_known():
    validate_no_leakage_columns(ENTRY_FILTER_COLUMNS)

    for field in fields(RealtimeLossProxyVariant):
        assert not any(term in field.name for term in FORBIDDEN_SIGNAL_FILTER_TERMS)


def test_realtime_variants_do_not_store_future_outcome_filters():
    for variant in build_realtime_loss_proxy_variants():
        validate_variant_no_leakage(variant)
        variant_text = repr(variant).lower()
        assert not any(term in variant_text for term in FORBIDDEN_SIGNAL_FILTER_TERMS)


def test_realtime_filter_functions_do_not_reference_outcome_columns():
    source = inspect.getsource(_side_allowed) + inspect.getsource(_side_setup_ok)
    source = source.lower()

    for term in FORBIDDEN_SIGNAL_FILTER_TERMS:
        assert term not in source


def test_no_leakage_filter_sources_are_research_only():
    checked_files = [
        Path("src/strategy_lab/v50_fast_loss_proxies.py"),
        Path("src/strategy_lab/v50_realtime_loss_proxy_sweep.py"),
    ]

    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        assert "live_broker" not in source
        assert "submit_order" not in source
        assert "api_key" not in source.lower()
        assert ".env" not in source
