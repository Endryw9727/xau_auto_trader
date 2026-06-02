# V2 Shadow Integration

## Scope

Sprint 1 integrates a small, isolated subset of the local V2 codebase into V1
as read-only shadow reporting under `src/v2_shadow/`.

Copied/adapted concepts:
- `ai_reasoning`: deterministic report-only scoring and explanations.
- `macro`: advisory local proxy snapshot, without external fetchers.
- `news`: warning-only shadow layer, without calendar API or scrapers.
- `smart_money`: diagnostic SMC overlay with explicit `available_at` for
  future-confirmed features.
- `indicators`: core pandas indicators for comparison diagnostics.

## Not Copied

The V2 broker, execution, scheduler, VPS automation, OANDA, IG, IB, ML,
continuous paper engine, MetaTrader execution, and live-trading modules were not
copied or imported. `PaperTradingEngineV2` is not used.

## Read-Only Safety

`src/v2_shadow` and `scripts/run_v2_shadow_report.py` only read V1 CSV/log data
and write shadow artifacts under `reports/shadow/`. They do not submit orders,
modify positions, call broker APIs, change V1 guardrails, or authorize/block
live trades. Macro, news, SMC, and AI output are advisory diagnostics only.

## Run

```bash
python scripts/run_v2_shadow_report.py --dry-run
```

Outputs:
- `reports/shadow/v2_shadow_latest.json`
- `reports/shadow/v2_shadow_latest.txt`

If no live V1 candidate/log context is available, the report status is
`NO_CANDIDATE` and still includes indicator, macro, news, SMC, and AI shadow
diagnostics when market data is available.

## Rollback

Remove these additions:
- `src/v2_shadow/`
- `scripts/run_v2_shadow_report.py`
- `tests/test_v2_shadow.py`
- `docs/V2_SHADOW_INTEGRATION.md`

No V1 live/demo execution, broker, scheduler, or safety configuration needs to
be changed for rollback because the integration is isolated.
