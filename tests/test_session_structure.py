import pandas as pd
import pytest

from src.analysis import session_structure as structure


def test_classify_session_matches_v50_windows():
    assert structure.classify_session(2) == "ASIA"
    assert structure.classify_session(9) == "ASIA/LONDON"
    assert structure.classify_session(12) == "LONDON"
    assert structure.classify_session(17) == "LONDON/US"
    assert structure.classify_session(20) == "NEW YORK"
    assert structure.classify_session(23) == "FX CLOSED"


def test_classify_session_rejects_bad_hour():
    with pytest.raises(ValueError):
        structure.classify_session(24)


def test_session_phase_mapping():
    assert structure.session_phase(2) == "ACCUMULATION"
    assert structure.session_phase(12) == "MANIPULATION"
    assert structure.session_phase(20) == "DISTRIBUTION"
    assert structure.session_phase(23) == "CLOSED"


def _candle(ts: str, o: float, h: float, low: float, c: float) -> dict:
    return {"Date": ts, "Open": o, "High": h, "Low": low, "Close": c, "Volume": 100}


def _sweep_low_reclaim_day() -> pd.DataFrame:
    # Asia builds a range 2000-2010; London sweeps below 2000 then closes back
    # inside (bullish manipulation); NY closes up (reversal long).
    rows = [
        _candle("2026-05-20 02:00:00", 2005, 2010, 2000, 2006),  # ASIA
        _candle("2026-05-20 05:00:00", 2006, 2009, 2001, 2004),  # ASIA
        _candle("2026-05-20 11:00:00", 2004, 2005, 1990, 1992),  # LONDON sweep low
        _candle("2026-05-20 12:00:00", 1992, 2007, 1991, 2006),  # LONDON reclaim into range
        _candle("2026-05-20 20:00:00", 2006, 2020, 2005, 2018),  # NY up
    ]
    return pd.DataFrame(rows)


def test_build_daily_structure_detects_sell_side_sweep_and_reclaim():
    result = structure.build_daily_structure(_sweep_low_reclaim_day())

    assert len(result) == 1
    row = result.iloc[0]
    assert row["asia_high"] == 2010.0
    assert row["asia_low"] == 2000.0
    assert bool(row["swept_asia_low"]) is True
    assert bool(row["swept_asia_high"]) is False
    assert row["sweep_side"] == "SELL_SIDE"
    assert bool(row["reclaimed_range"]) is True
    assert row["manipulation_label"] == "london_sweep_low_reclaimed"
    assert row["ny_direction"] == "UP"


def test_build_daily_structure_no_sweep():
    rows = [
        _candle("2026-05-21 02:00:00", 2005, 2010, 2000, 2006),  # ASIA
        _candle("2026-05-21 11:00:00", 2004, 2008, 2002, 2005),  # LONDON inside range
        _candle("2026-05-21 20:00:00", 2005, 2006, 2003, 2004),  # NY down
    ]
    result = structure.build_daily_structure(pd.DataFrame(rows))

    row = result.iloc[0]
    assert row["sweep_side"] == "NONE"
    assert bool(row["reclaimed_range"]) is False
    assert row["manipulation_label"] == "no_sweep"
    assert row["ny_direction"] == "DOWN"


def test_reclaim_ignores_pre_sweep_close():
    # London closes INSIDE the Asia range first, then sweeps the high and stays
    # above (no reclaim). The early in-range close must not count as a reclaim.
    rows = [
        _candle("2026-05-24 02:00:00", 2005, 2010, 2000, 2006),  # ASIA range 2000-2010
        _candle("2026-05-24 11:00:00", 2005, 2008, 2002, 2004),  # LONDON inside range
        _candle("2026-05-24 12:00:00", 2004, 2025, 2004, 2024),  # LONDON sweep high, stays above
    ]
    result = structure.build_daily_structure(pd.DataFrame(rows))

    row = result.iloc[0]
    assert row["sweep_side"] == "BUY_SIDE"
    assert bool(row["reclaimed_range"]) is False
    assert row["manipulation_label"] == "sweep_not_reclaimed"


def test_build_daily_structure_buy_side_sweep_without_reclaim():
    rows = [
        _candle("2026-05-22 02:00:00", 2005, 2010, 2000, 2006),  # ASIA
        _candle("2026-05-22 11:00:00", 2006, 2025, 2006, 2024),  # LONDON sweep high, stays above
    ]
    result = structure.build_daily_structure(pd.DataFrame(rows))

    row = result.iloc[0]
    assert row["sweep_side"] == "BUY_SIDE"
    assert bool(row["reclaimed_range"]) is False
    assert row["manipulation_label"] == "sweep_not_reclaimed"


def test_build_daily_structure_groups_multiple_days():
    data = pd.concat([_sweep_low_reclaim_day(), _sweep_low_reclaim_day().assign(Date=lambda d: d["Date"].str.replace("05-20", "05-23"))])
    result = structure.build_daily_structure(data)
    assert len(result) == 2


def test_distance_from_levels_picks_nearest():
    row = {"asia_high": 2010.0, "asia_low": 2000.0, "london_high": None, "london_low": None}
    dist = structure.distance_from_levels(2001.0, row)

    assert dist.nearest_level_name == "asia_low"
    assert dist.nearest_level_price == 2000.0
    assert dist.distance == pytest.approx(1.0)
    assert dist.in_asia_range is True


def test_distance_from_levels_out_of_range():
    row = {"asia_high": 2010.0, "asia_low": 2000.0}
    dist = structure.distance_from_levels(2015.0, row)

    assert dist.nearest_level_name == "asia_high"
    assert dist.in_asia_range is False
    assert dist.distance == pytest.approx(5.0)


def test_distance_from_levels_no_levels():
    dist = structure.distance_from_levels(2000.0, {"asia_high": None, "asia_low": None})
    assert dist.nearest_level_name == "none"
    assert dist.distance is None


def test_build_daily_structure_empty():
    assert structure.build_daily_structure(pd.DataFrame()).empty


def test_module_has_no_execution_imports():
    from pathlib import Path

    source = Path("src/analysis/session_structure.py").read_text(encoding="utf-8")
    assert "order_send" not in source
    assert "from src.execution" not in source
    assert "import src.execution" not in source
    assert "run_v51_demo_execution_once" not in source
