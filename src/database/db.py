"""
SQLite database utilities.

This module creates the SQLite database and provides helper functions
for saving and reading signals, trades, stats, equity snapshots, and errors.

The database is local and intended for backtesting and paper trading.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from src.database.models import Base, DailyStats, EquityCurve, ErrorLog, Signal, Trade


DEFAULT_DB_PATH = Path("data/database/trading.db")


def get_database_url(db_path: str | Path = DEFAULT_DB_PATH) -> str:
    """Return a SQLite database URL from a path."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def create_db_engine(db_path: str | Path = DEFAULT_DB_PATH):
    """Create a SQLAlchemy engine for the SQLite database."""
    return create_engine(get_database_url(db_path), echo=False, future=True)


def init_database(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    """Create all database tables if they do not exist."""
    engine = create_db_engine(db_path)
    Base.metadata.create_all(engine)


def get_session_factory(db_path: str | Path = DEFAULT_DB_PATH):
    """Return a configured SQLAlchemy session factory."""
    engine = create_db_engine(db_path)
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def save_signal(signal: Signal, db_path: str | Path = DEFAULT_DB_PATH) -> Signal:
    """Save a Signal record and return it with its database ID."""
    SessionLocal = get_session_factory(db_path)
    with SessionLocal() as session:
        session.add(signal)
        session.commit()
        session.refresh(signal)
        return signal


def save_trade(trade: Trade, db_path: str | Path = DEFAULT_DB_PATH) -> Trade:
    """Save a Trade record and return it with its database ID."""
    SessionLocal = get_session_factory(db_path)
    with SessionLocal() as session:
        session.add(trade)
        session.commit()
        session.refresh(trade)
        return trade


def save_daily_stats(stats: DailyStats, db_path: str | Path = DEFAULT_DB_PATH) -> DailyStats:
    """Save a DailyStats record."""
    SessionLocal = get_session_factory(db_path)
    with SessionLocal() as session:
        session.add(stats)
        session.commit()
        session.refresh(stats)
        return stats


def save_equity_snapshot(snapshot: EquityCurve, db_path: str | Path = DEFAULT_DB_PATH) -> EquityCurve:
    """Save an EquityCurve snapshot."""
    SessionLocal = get_session_factory(db_path)
    with SessionLocal() as session:
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)
        return snapshot


def save_error(error: ErrorLog, db_path: str | Path = DEFAULT_DB_PATH) -> ErrorLog:
    """Save an error log entry."""
    SessionLocal = get_session_factory(db_path)
    with SessionLocal() as session:
        session.add(error)
        session.commit()
        session.refresh(error)
        return error


def get_all_signals(db_path: str | Path = DEFAULT_DB_PATH) -> list[Signal]:
    """Return all saved signals."""
    SessionLocal = get_session_factory(db_path)
    with SessionLocal() as session:
        return list(session.scalars(select(Signal)).all())


def get_all_trades(db_path: str | Path = DEFAULT_DB_PATH) -> list[Trade]:
    """Return all saved trades."""
    SessionLocal = get_session_factory(db_path)
    with SessionLocal() as session:
        return list(session.scalars(select(Trade)).all())


def count_records(model: type[Base], db_path: str | Path = DEFAULT_DB_PATH) -> int:
    """Count rows for a given model."""
    SessionLocal = get_session_factory(db_path)
    with SessionLocal() as session:
        return len(list(session.scalars(select(model)).all()))
