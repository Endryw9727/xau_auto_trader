# XAU Auto Trader Paper Trading Runbook

This runbook is for controlled paper/research only. It does not authorize live
trading, broker execution, API keys, or any change to `LIVE_MODE=false`.

## Frozen Paper Decision

- Paper main strategy: `proxy_hardened_no_worst_hours_high_margin`
- Research comparison strategy: `proxy_hardened_no_worst_hours`
- Emergency/research mode: `dynamic_normal_defensive_pause`
- Live trading: disabled
- `allow_live`: `false`

## Why High-Margin Is The Paper Main

`proxy_hardened_no_worst_hours_high_margin` is the main paper candidate because
it keeps the recent quality profile stronger than the original main:

- PF last 30: about `1.497`
- PF last 50: about `1.661`
- max drawdown: about `7.47%`
- trade/day: about `0.517`

It gives up some total equity growth and frequency, but it stays closer to the
current paper risk limits. For a 1000 EUR controlled paper phase, that tradeoff
is preferable to running a higher-warning variant.

## Why Dynamic Is Not The Main

`dynamic_normal_defensive_pause` is useful as an emergency/research diagnostic,
but it cuts too much activity:

- trade/day: about `0.185`
- total trades: `243`
- ending equity: about `1247.83 EUR`

It reduces drawdown, but the trade frequency is too low for the current paper
objective. It stays available only as an emergency/research reference.

## Risk Rules With 1000 EUR

- Starting equity: `1000 EUR`
- Lot size: `0.01` lots from `1000` to `1999 EUR`
- Lot step: `+0.01` every `+1000 EUR`
- Research max lot: `0.10`
- Max trades/day: `2`
- Max daily loss: `3%`
- Max weekly loss: `8%`
- Warning drawdown: `8%`
- Stop drawdown: `12%`
- Paper only: no real orders

## Daily Checklist

Before starting:

```bash
python scripts/paper_preflight_check.py
```

Check local data freshness when preparing a paper-forward session:

```bash
.venv/bin/python scripts/check_data_freshness.py
```

During the session, after each newly closed local candle:

```bash
python scripts/run_paper_forward_once.py
```

After the paper session:

```bash
python scripts/paper_end_of_day_report.py
python scripts/paper_forward_status.py
python scripts/paper_daily_report.py
python scripts/check_paper_validation_status.py
```

Also review:

- current equity
- current and max drawdown
- total PF
- PF last 30 and last 50
- daily and weekly loss
- current loss streak
- whether status is `OK`, `WARNING`, or `STOP`

## Data Freshness Rules

Fresh local XAUUSD data is mandatory because paper-forward evaluates the latest
closed candle. If the local CSV is stale, the strategy would be reasoning on an
old market state, so new paper trades must be paused.

Freshness states:

- `OK`: latest 15m candle is within `30` minutes.
- `WARNING`: latest 15m candle is older than `30` minutes and up to `90`
  minutes. Continue only with controlled caution.
- `STALE`: latest 15m candle is older than `90` minutes. The system goes to
  `PAUSE` and must not generate a new paper trade.
- `ERROR`: file missing, empty data, invalid timestamps, or timeframe not
  detectable. The system goes to `PAUSE` with `DATA_ERROR`.

If data is `STALE`, update the local XAUUSD CSV first, rerun:

```bash
.venv/bin/python scripts/check_data_freshness.py
```

Then run preflight again before any paper-forward evaluation.

## Demo Broker Read-Only Phase

The demo broker phase is read-only. It may inspect an Axi/MetaTrader demo
account later, but it must not open demo trades, real trades, or any broker
orders.

Current rules:

- `config/demo_broker.yaml` must keep `demo_only: true`.
- `allow_live` must stay `false`.
- `execution_enabled` must stay `false`.
- MT5 connectivity is optional in this phase; if it is not configured, the
  check runs in `MT5_NOT_CONNECTED_MOCK_ONLY` mode.
- This phase is only for comparing local paper data with broker-side account,
  symbol, spread, and position snapshots.
- Demo execution can be discussed only in a separate future phase.
- Real live trading remains forbidden.

Check the read-only demo broker guardrails with:

```bash
.venv/bin/python scripts/check_demo_broker_readonly.py
```

## Stop Paper Immediately

Stop opening new paper trades and review if any of these happen:

- daily loss exceeds `3%`
- weekly loss exceeds `8%`
- drawdown exceeds `12%`
- PF last 50 falls below `1.00`
- current loss streak exceeds the configured emergency threshold
- fills, spread, commission, or slippage differ materially from the paper model

## Use Extra Prudence

Treat the day as warning/strict-observation if:

- drawdown is above `8%`
- PF last 50 is below `1.05`
- PF last 30 is below the monitor threshold
- recent trade quality degrades in New York or around hour `18`

## Passing From Paper To Demo

Demo discussion can start only after:

- at least `30` paper days
- at least `100` paper trades preferred
- net PF remains above `1.20`
- recent PF last 50 remains above `1.05`
- max drawdown stays below the stop level
- no paper stop rule is breached

This is still not live trading.

## When Not To Pass Live

Do not pass to live if:

- `allow_live=false`
- `LIVE_MODE=false` has not been explicitly revisited in a separate future task
- paper is in `WARNING` or `STOP`
- recent PF is below thresholds
- drawdown or loss streak is above limits
- broker costs/fills are not verified with paper statements

No strategy is promoted automatically.
