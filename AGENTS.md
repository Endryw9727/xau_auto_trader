# AGENTS.md - XAU Auto Trader

## Project goal

This project is a Python modular trading research system for XAU/USD.

It supports:
- OHLCV CSV loading
- technical indicators
- market structure analysis
- signal generation
- risk management
- backtesting
- paper trading
- SQLite trade journal
- Streamlit dashboard
- protected live broker interface

## Safety rules

Never implement real live trading without explicit user approval.

Current live trading rules:
- LIVE_MODE must remain false by default
- no real broker API calls
- no real orders
- no API keys in code
- no .env committed to Git
- every tradable signal must have stop loss
- every trade must pass the risk manager
- live_broker.py must remain protected by tests

## Environment

Use Python virtual environment:

    source .venv/bin/activate

Install dependencies:

    pip install -r requirements.txt

Run tests:

    pytest

Run local backtest:

    python -m src.main

Run paper trading simulation:

    python scripts/run_paper_trading.py

Run dashboard:

    streamlit run src/dashboard/dashboard.py

## Coding rules

- Keep modules small and testable.
- Add or update tests for every code change.
- Do not break existing tests.
- Prefer simple, readable Python.
- Do not add heavy dependencies unless necessary.
- Do not commit generated CSV files, reports, databases, .venv, or .env.
- Respect config.yaml as the source of adjustable strategy/risk parameters.

## Current roadmap

Next useful improvements:
1. Save generated signals to SQLite.
2. Add signals tab to Streamlit dashboard.
3. Add session analysis: London / New York.
4. Add better strategy diagnostics.
5. Add real OHLCV CSV import validation.
6. Add broker demo integration only after explicit approval.
