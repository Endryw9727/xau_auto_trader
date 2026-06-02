# V51 Time Alignment

## Scope

V51 compares MT5 CSV candle timestamps, VPS wall-clock time, UTC audit time,
and candidate freshness gates. The execution layer stays demo-safe: this
document does not introduce live trading, broker permissions, or relaxed
guards.

## Timestamp Rule

MT5 CSV timestamps without timezone information are interpreted as broker/local
wall-clock time using:

```yaml
mt5_timestamp_timezone: Europe/Rome
```

If the key is missing, `Europe/Rome` is used by default. Timezone-aware
timestamps are converted to UTC and are not localized a second time.

Example during CEST:

```text
raw MT5 CSV timestamp: 2026-06-02 23:45:00
timezone: Europe/Rome
UTC comparison time: 2026-06-02 21:45:00+00:00
```

## Internal Comparisons

The following checks use UTC-aware timestamps internally:

- latest closed candle selection
- candidate freshness age
- `candidate_time_in_future`
- `candidate_stale`
- `require_latest_closed_candle_candidate`
- V51 live-safe decision audit

The latest closed candle helper excludes the currently open candle by requiring:

```text
candle_open_time + timeframe <= now_utc
```

This prevents lookahead when a CSV already contains the current in-progress M15
candle.

## Audit Fields

`reports/demo_execution/v51_decision_audit.csv` includes both raw and normalized
timestamps:

- `now_utc`
- `now_local`
- `mt5_timestamp_timezone`
- `latest_closed_candle_time_raw`
- `latest_closed_candle_time_utc`
- `selected_candidate_time_raw`
- `selected_candidate_time_utc`
- `candidate_age_minutes`
- `candidate_time_basis`
- `time_alignment_status`

Use these fields to diagnose false future/stale conditions on the VPS. A true
future candidate remains rejected with `candidate_time_in_future` after UTC
normalization.

## Safety

This alignment layer does not:

- enable real live trading
- change `allow_real_live`
- disable `require_latest_closed_candle_candidate`
- bypass `candidate_time_in_future`
- loosen slippage, freshness, duplicate, MTF, or demo execution guards
- authorize orders from V2 shadow modules
