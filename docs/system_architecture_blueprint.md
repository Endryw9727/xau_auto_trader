# XAU Auto Trader System Architecture Blueprint

This blueprint describes the long-term modular architecture for XAU Auto
Trader. It is intentionally paper/research first. It does not authorize live
trading, broker execution, API keys, or any change to `LIVE_MODE=false` and
`allow_live=false`.

## Current Safety Position

- Frozen paper candidate: `proxy_hardened_no_worst_hours_high_margin`
- Current mode: local paper-forward and research only
- Live trading: disabled
- `LIVE_MODE`: false
- `allow_live`: false
- Execution: future-only, manually approved, separated from research modules
- AI: advisory only, cannot execute and cannot bypass risk checks

## Block Workflow

```text
Market Data Layer
        |
        v
Technical Strategy Layer ---- Macro Fundamental Layer
        |                            |
        +------------+---------------+
                     v
              AI Reasoning Layer
              advisory only
                     |
                     v
                Risk Engine
                     |
                     v
             Paper Forward Layer
                     |
                     v
       Monitoring and Telegram Layer
                     |
                     v
          Future Execution Layer
          disabled until manual approval
```

## 1. Market Data Layer

Purpose:

- Load and validate local XAUUSD OHLCV data.
- Support multi-timeframe datasets such as M1, M5, M15, M30, H1, and H4.
- Prepare future external context inputs such as DXY, US10Y, and news/calendar
  files.
- Run freshness checks before paper-forward decisions.
- Detect data quality issues: empty files, invalid timestamps, duplicate
  candles, missing expected candles, temporal gaps, stale local data.

Current modules:

- `src/data_feed/market_data.py`
- `src/market_data/timeframe_loader.py`
- `src/market_data/data_freshness.py`

Future extensions:

- Local DXY CSV loader.
- Local US10Y CSV loader.
- Economic calendar file parser.
- News risk snapshot loader.

Safety rules:

- The layer may read local files only unless a future explicit task approves a
  safe data connector.
- It must not place orders.
- It must not import broker execution code.
- Stale or invalid data must block new paper-forward signals.

## 2. Technical Strategy Layer

Purpose:

- Generate technical BUY, SELL, or NO_TRADE signals.
- Keep `proxy_hardened_no_worst_hours_high_margin` frozen as the controlled
  paper candidate.
- Calculate entry, stop loss, take profit, technical score, score gap,
  sessions, and strategy reasons.
- Apply realtime-safe filters only. No filter may use future information such
  as PnL, exit time, bars in trade, or post-trade drawdown.

Current responsibilities:

- V50 technical feature generation.
- High-margin candidate filtering.
- Session filtering.
- Score and score-gap quality checks.
- SL/TP generation through existing strategy configuration.

Safety rules:

- The strategy layer returns analytical signals only.
- It must not execute trades.
- It must not change frozen paper-candidate logic without a before/after
  comparison and explicit review.

## 3. Macro Fundamental Layer

Purpose:

- Build a macro context snapshot for XAUUSD decisions.
- Track DXY bias, US yields bias, risk sentiment, and high-impact news risk.
- Identify periods such as CPI, NFP, FOMC, Powell speeches, and other high
  impact events.
- Produce macro scores that support or warn against LONG/SHORT technical
  setups.

Output concept:

- `MacroSnapshot`
- `dxy_bias`
- `yields_bias`
- `news_risk`
- `risk_sentiment`
- `macro_score_long`
- `macro_score_short`
- `notes`

Safety rules:

- Macro context is advisory.
- It must not generate orders by itself.
- It must not override the risk engine.
- Missing macro data should default to neutral or warning, never to forced
  trading.

## 4. AI Reasoning Layer

Purpose:

- Combine technical snapshot, macro snapshot, and risk state into an explanation.
- Return an advisory recommendation:
  - `WAIT`
  - `SUPPORT_BUY`
  - `SUPPORT_SELL`
  - `BLOCK`
- Explain why a paper-forward signal is supported, risky, or blocked.
- Emit confidence and warnings for reports.

Inputs:

- Technical score long/short.
- Macro snapshot.
- Current risk state.
- Paper mode flag.
- `allow_live` flag.

Outputs:

- Explanation.
- Confidence.
- Warning list.
- No-trade reason when relevant.
- `ai_can_execute = False` always.

Safety rules:

- AI is advisory only.
- AI cannot open, close, or modify orders.
- AI cannot bypass the risk engine.
- AI cannot turn `allow_live` on.
- AI cannot promote a strategy automatically.

## 5. Risk Engine

Purpose:

- Protect account-level paper-forward operation.
- Enforce sizing, loss limits, drawdown limits, and loss-streak guards.

Current paper sizing:

- Initial capital: `1000 EUR`
- Initial size: `0.01` lots
- Size ladder: `0.02` lots from `2000 EUR`, then `+0.01` per additional
  `1000 EUR`
- Research max lot: `0.10`
- Broker model: Axi Pro style research costs
- Commission: `0.04 EUR` per `0.01` lots per side

Guards:

- Max daily loss.
- Max weekly loss.
- Max trades per day.
- Drawdown warning and stop.
- Loss streak warning and stop.
- Freshness gate before paper-forward.

Safety rules:

- Risk engine is mandatory for every paper-forward decision.
- No advisory layer may bypass it.
- If risk state is STOP, new signals must be blocked.

## 6. Paper Forward Layer

Purpose:

- Run controlled local paper-forward decisions from the latest closed candle.
- Register paper signals.
- Register open and closed paper trades.
- Maintain paper equity curve.
- Generate daily logs and status.

Current files:

- `reports/paper_forward/paper_forward_signals.csv`
- `reports/paper_forward/paper_forward_open_trades.csv`
- `reports/paper_forward/paper_forward_closed_trades.csv`
- `reports/paper_forward/paper_forward_equity.csv`
- `reports/paper_forward/paper_forward_daily_log.csv`
- `reports/paper_forward/data_freshness_log.csv`

Decision states:

- `NO_TRADE`
- `PAPER_BUY`
- `PAPER_SELL`
- `PAUSE`
- `STOP`

Safety rules:

- Paper-forward never sends real orders.
- Paper-forward must pause on stale data.
- Paper-forward must stop when risk limits are breached.

## 7. Monitoring And Telegram Layer

Purpose:

- Produce daily and intraday paper status.
- Summarize signals, open trades, closed trades, equity, drawdown, recent PF,
  and warnings.
- Prepare future Telegram-friendly report models.

Report types:

- Daily paper report.
- Paper-forward status.
- Signal report.
- Warning report.
- STOP report.
- Open-trade summary.
- Closed-trade summary.

Safety rules:

- Telegram/reporting is notification-only.
- Telegram must not execute trades.
- Telegram must not expose API keys.
- Any Telegram integration must be optional and disabled until configured
  safely in a future task.

## 8. Future Execution Layer

Purpose:

- Reserved placeholder for a future broker connector.
- Must remain disabled until manual approval after paper/demo validation.
- Must remain separated from strategy, AI, and monitoring modules.

Required future gates before any implementation:

- Explicit user approval.
- Demo-only connector first.
- New tests proving `LIVE_MODE=false` remains default.
- New tests proving no real orders can be sent unless an explicit manual live
  switch is present.
- Separate audit of broker costs, market hours, position sizing, and emergency
  shutdown behavior.

Current state:

- Disabled.
- `allow_live=false`.
- No execution functions.
- No broker API calls.
- No API keys.

## Non-Negotiable Guardrails

- Paper trading first.
- AI advisory only.
- Risk engine is mandatory.
- Live trading is disabled.
- Execution layer is future-only.
- No automatic strategy promotion.
- No API keys in code.
- No `.env` changes.
- No real orders.
