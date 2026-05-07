import pandas as pd
import pytest

from src.analysis.session_analysis import (
    add_session_column,
    calculate_session_summary,
    classify_hour_to_session,
)


def test_classify_hour_to_session():
    assert classify_hour_to_session(1) == "Asia"
    assert classify_hour_to_session(9) == "London"
    assert classify_hour_to_session(15) == "New York"
    assert classify_hour_to_session(22) == "Off Session"


def test_classify_hour_invalid_raises_error():
    with pytest.raises(ValueError):
        classify_hour_to_session(24)


def test_add_session_column():
    trades = pd.DataFrame(
        {
            "timestamp_open": [
                "2026-01-01 01:00:00",
                "2026-01-01 09:00:00",
                "2026-01-01 15:00:00",
                "2026-01-01 22:00:00",
            ],
            "profit_loss": [1.0, 2.0, 3.0, -1.0],
        }
    )

    result = add_session_column(trades)

    assert "session" in result.columns
    assert result.iloc[0]["session"] == "Asia"
    assert result.iloc[1]["session"] == "London"
    assert result.iloc[2]["session"] == "New York"
    assert result.iloc[3]["session"] == "Off Session"


def test_calculate_session_summary():
    trades = pd.DataFrame(
        {
            "session": ["London", "London", "New York", "New York"],
            "profit_loss": [10.0, -5.0, 20.0, 0.0],
        }
    )

    summary = calculate_session_summary(trades)

    assert len(summary) == 2
    assert "net_profit" in summary.columns
    assert summary["total_trades"].sum() == 4
