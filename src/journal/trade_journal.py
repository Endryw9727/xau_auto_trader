"""
Trade journal for SQLite persistence.

This module handles saving trades to a local SQLite database.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import sqlite3

DB_PATH = Path("data/database/trading.db")

def save_trades_dataframe_to_db(trades_df: pd.DataFrame, mode: str = "backtest") -> int:
    """
    Save trades DataFrame to SQLite database.

    Parameters:
    - trades_df: DataFrame with trade records
    - mode: 'backtest' or 'paper' or 'live'

    Returns:
    - Number of trades inserted
    """
    if trades_df.empty:
        return 0

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    trades_to_save = trades_df.copy()
    trades_to_save["mode"] = mode

    trades_to_save.to_sql("trades", conn, if_exists="append", index=False)

    conn.close()

    return len(trades_to_save)

def get_all_trades(mode: str | None = None) -> pd.DataFrame:
    """Retrieve trades from database."""
    if not DB_PATH.exists():
        return pd.DataFrame()

    conn = sqlite3.connect(DB_PATH)

    if mode:
        query = f"SELECT * FROM trades WHERE mode = '{mode}'"
    else:
        query = "SELECT * FROM trades"

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df
