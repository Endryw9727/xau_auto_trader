# Pine V50 Translation Plan

## Scope

Reference file analyzed:

- `reference/xau_v50_strategy.pine`

This plan is for research/backtest only. It does not add live trading, broker
execution, API keys, or order routing.

## Data Timeframe Check

`data/raw/xauusd.csv` currently starts with:

- `2022-02-11 11:00:00`
- `2022-02-11 11:15:00`

The local CSV is therefore 15m data.

The Pine strategy uses 4H, 1H, 15M, 10M, and 5M data. With only 15m candles,
the Python project can resample upward to 1H and 4H and can use native 15M, but
it cannot faithfully reconstruct 10M or 5M trigger candles. Phase 1 therefore
marks V50 as an approximation and uses the base 15m feed for 10m/5m trigger
proxies when lower-timeframe data is missing.

If future input data is 5m or lower, the project can resample to 10M, 15M, 1H,
and 4H and remove most of this timeframe approximation.

## Technical Features Needed

- Multi-timeframe OHLCV packs for 4H, 1H, 15M, 10M, and 5M.
- EMA 21, EMA 50, EMA 200 on each timeframe.
- EMA 50 slope on higher timeframes.
- RSI 14.
- Williams %R 24.
- ADX / +DI / -DI 14.
- ATR 14.
- Volume ratio vs rolling average.
- Session VWAP.
- Rolling POC and POC zone.
- Round levels and round-level danger zones.
- Swing pivot highs/lows.
- BOS, weak BOS, CHOCH, sweep, retest, recent structure shift.
- Pullback and momentum-cross triggers.
- DXY and US10Y proxy trend packs on 1H.
- ATR regime ratio, shock/headline regime, decoupled regime, trend-day regime.
- Session labels and time-quality windows.
- Anti-chase, RSI exhaustion, late impulse guard, chop/compression guard.
- LONG/SHORT scores and reversal/continuation/range sub-scores.

## LONG Conditions

The Pine has several LONG families. The main sniper/trend path requires:

- 4H bullish trend or soft bullish 4H bias.
- 1H bullish momentum: close above EMA 50, +DI above -DI, ADX active, RSI above 52.
- 15M bullish structure: close above EMA 200, EMA 21 above EMA 50, RSI above 50.
- 10M and 5M bullish trigger confirmation.
- Structure trigger from sweep, retest, first breakout, or allowed continuation pullback.
- Close above local EMA 21 with +DI above -DI and active ADX.
- ScoreLong above dynamic threshold.
- ScoreLong ahead of ScoreShort by the configured score gap.
- Enough MTF confirmations.
- Intermarket confirmation unless neutralized by shock/decoupled regime.
- Quality filters pass: value area, no chop, no chase, no RSI exhaustion, no late impulse, no weak BOS, no round-level block.
- Regime filter does not block LONG, or a counter-trend exception is valid.
- Session and time-quality filters allow the trade.
- Cooldown rules allow a new LONG.

Reversal LONG adds stricter CHOCH/sweep/retest quality and recent bullish shift
conditions. Continuation and range scalp modes are optional playbooks in the
Pine and are not implemented in phase 1.

## SHORT Conditions

The SHORT side mirrors the LONG logic:

- 4H bearish trend or soft bearish 4H bias.
- 1H bearish momentum: close below EMA 50, -DI above +DI, ADX active, RSI below 48.
- 15M bearish structure: close below EMA 200, EMA 21 below EMA 50, RSI below 50.
- 10M and 5M bearish trigger confirmation.
- Structure trigger from sweep, retest, first breakout, or allowed continuation pullback.
- Close below local EMA 21 with -DI above +DI and active ADX.
- ScoreShort above dynamic threshold.
- ScoreShort ahead of ScoreLong by the configured score gap.
- Enough MTF confirmations.
- Intermarket confirmation unless neutralized by shock/decoupled regime.
- Quality filters pass: value area, no chop, no chase, no RSI exhaustion, no late impulse, no weak BOS, no round-level block.
- Regime filter does not block SHORT, or a counter-trend exception is valid.
- Session and time-quality filters allow the trade.
- Cooldown rules allow a new SHORT.

## Blocking Filters

- Closed FX window and forced intraday flat window.
- Manual macro/news block.
- Optional volume filter.
- Time guards: early Asia, mid-London chop, London fix/news spike.
- Session quality guard and adaptive London quality guard.
- NY weak SHORT guard.
- NY weak/tardy LONG guards.
- HTF regime anti-trend filter.
- VWAP/POC value filter.
- POC/VWAP compression chop.
- Anti-chase extension from EMA 50.
- RSI exhaustion.
- Late impulse and post-impulse trap.
- Weak BOS.
- Round-level danger filter.
- Cooldown after sniper signal and after losses by direction.
- Dynamic invalidation while a plan is active.

## Risk Management Rules

- Pine account/risk profile inputs: account size, risk percent, USD per point,
  fixed backtest quantity, pip value.
- Stop calculation uses recent swing/structure levels, ATR buffer, min/max stop
  pips, optional structure stop stretch.
- TP1, TP2, TP3 use RR targets with optional swing-level adjustment.
- Partial exits: 33% at TP1, 33% at TP2, 34% at TP3.
- Move remaining stop to break-even after TP1.
- Dynamic invalidation can close the active plan if score, structure, or adverse
  ATR conditions deteriorate.
- Intraday flat can close positions near the end of the trading day.
- Size can be adjusted by signal score, risk profile, direction, and regime.

The current Python backtester supports one stop and one take-profit per trade,
not TP1/TP2/TP3 partial exits or BE-after-TP1. A phase 2 backtester extension is
needed before the Pine risk model can be replicated.

## Pine Details Difficult To Replicate

- TradingView `request.security` alignment and closed HTF candle behavior.
- 5m and 10m lower-timeframe triggers from a 15m-only CSV.
- Tick-level behavior from `calc_on_every_tick` and order-fill recalculation.
- Strategy partial exits and stop updates after TP1.
- Stateful arrays of pivot levels and nearest support/resistance selection.
- Rolling POC with volume buckets exactly matching Pine array logic.
- Session timezone and daylight-saving behavior.
- DXY and US10Y proxy requests from TradingView symbols.
- Dynamic invalidation state and per-direction loss cooldown state.
- Visual/dashboard-only state does not map to Python research output.

## Missing Data In The Current Project

- 5m or lower XAUUSD OHLCV.
- 10m derived candles from lower timeframe.
- DXY OHLCV.
- US10Y OHLCV.
- TradingView session/timezone metadata.
- Tick/intrabar order-fill sequence.
- Volume quality may be weak if CSV volume is tick count or constant.

## Phase 1 Python Implementation

Implemented candidate:

- `src/strategy_lab/strategy_v50_pine.py`
- Strategy Lab name: `v50_pine_technical_strategy`

Phase 1 includes:

- EMA 21/50/200.
- RSI.
- Williams %R.
- ADX / +DI / -DI.
- ATR.
- 4H, 1H, 15M resampled or native features.
- 10M and 5M approximation when lower timeframe data is unavailable.
- Macro neutral mode when DXY/US10Y data is unavailable.
- Base scoreLong / scoreShort.
- Session filter.
- Simple anti-chase.
- Simple late impulse and chop guards.
- BUY / SELL / NO_TRADE output compatible with the current backtester.

Not implemented in phase 1:

- Real DXY/US10Y feeds.
- Rolling POC bucket model.
- Full CHOCH/retest state machine.
- Continuation and range playbook modes.
- TP1/TP2/TP3 partial exits.
- Break-even stop migration after TP1.
- Dynamic invalidation exits.
- Real broker execution.
