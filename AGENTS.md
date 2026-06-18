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
- allow_real_live must remain false unless Andrei explicitly authorizes a controlled change
- no real broker API calls by default
- no real orders by default
- no API keys in code
- no .env committed to Git
- every tradable signal must have stop loss
- every trade must pass the risk manager
- live_broker.py must remain protected by tests

Any autonomous/demo/live execution must include:
- max trades per day
- max daily loss
- max position size
- kill switch
- news/session filter if available
- explicit logs for every rejected trade

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
- Respect config.yaml and strategy YAML files as the source of adjustable strategy/risk parameters.
- Never weaken risk filters just to force more trades.
- First log rejection reasons, then decide whether a filter is too strict.

## Current priority - rejection diagnostics

Before adding new strategies, inspect why trade candidates are rejected.

Useful files:

- reports/demo_execution/v51_demo_execution_log.csv
- reports/demo_execution/v51_live_safe_cycle.log
- reports/diagnostics/v51_mtf_context_latest.txt
- reports/diagnostics/v51_mtf_context_summary.csv

Expected diagnostic output:

- total candidates
- accepted demo candidates
- rejected candidates
- rejection reasons grouped by count
- top blocking filter
- whether the block is safety-critical or probably too strict
- recommended next modification

## V Formation research module

The V Formation strategy must be implemented as a separate research module, not by overwriting the current strategy.

Concept:

- Session filter: primarily London / New York for XAU/USD.
- Higher timeframe bias: D1 / H4 / H1.
- Setup timeframe: M15 / M5.
- Fine trigger timeframe: M5 / M1.
- Long only with LONG_BIAS.
- Short only with SHORT_BIAS.
- No trade with MIXED or NO_TRADE_CONTEXT.
- V Formation must occur in a coherent zone, not randomly.

Long setup idea:

1. HTF bias is long.
2. Price is in discount or under the local 50 percent range.
3. Price sweeps liquidity below a recent low.
4. Price quickly reclaims the swept level.
5. Micro BOS or CHOCH confirms bullish control.
6. Entry on retest or controlled pullback.
7. SL below the V low.
8. TP toward reachable upper liquidity with minimum RR.

Short setup idea:

1. HTF bias is short.
2. Price is in premium or above the local 50 percent range.
3. Price sweeps liquidity above a recent high.
4. Price quickly rejects below the swept level.
5. Micro BOS or CHOCH confirms bearish control.
6. Entry on retest or controlled pullback.
7. SL above the V high.
8. TP toward reachable lower liquidity with minimum RR.

Do not treat the V shape alone as a valid entry. The V is only a trigger after session, bias, zone, reachability and risk filters pass.

## Recommended roadmap

1. Add rejection diagnostics command/report.
2. Add session and reachability diagnostics.
3. Add VFormationDetector as research-only module.
4. Add tests with synthetic patterns.
5. Backtest on historical XAU/USD data.
6. Paper trade.
7. Demo-only execution after review.
8. Real live execution only after explicit approval and strong evidence.
