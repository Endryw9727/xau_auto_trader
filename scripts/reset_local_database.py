"""
Reset local SQLite database.

Usage:
    python scripts/reset_local_database.py

This deletes only:
    data/database/trading.db

It does not delete code, reports, CSV data, or configuration files.
"""

from pathlib import Path


DATABASE_PATH = Path("data/database/trading.db")


def main() -> None:
    """Delete local SQLite database if it exists."""
    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()
        print(f"Deleted database: {DATABASE_PATH}")
    else:
        print(f"Database not found, nothing to delete: {DATABASE_PATH}")

    print("")
    print("Next recommended commands:")
    print("python -m src.main")
    print("python scripts/run_paper_trading.py")
    print("streamlit run src/dashboard/dashboard.py")


if __name__ == "__main__":
    main()
