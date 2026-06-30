# CLAUDE.md — XAU Auto Trader

Guida operativa per agenti AI (Claude/Codex) e sviluppatori che lavorano su
questo repository. Va letta **prima** di qualsiasi modifica.

---

## 1. Descrizione del progetto

Sistema quantitativo/diagnostico modulare in Python, nato su **XAU/USD** e in
estensione **multi-strumento** (indici tipo NAS100, FX major: EURUSD, AUDUSD,
GBPUSD, USDJPY, USDCAD).

Non è (e non deve diventare) un bot aggressivo che apre trade a caso. È prima di
tutto una **macchina di validazione, diagnostica, filtro e osservazione
statistica** che analizza price action, sessioni, liquidità, bias
multi-timeframe, qualità dei setup e rischio **prima** di qualunque esecuzione.
La ricerca dell'edge è **per-strumento**: si cerca un vantaggio statistico
robusto (in-sample + out-of-sample, al netto dei costi) e si **escludono** gli
strumenti dove non emerge (`scripts/run_session_edge_lab.py`).

Layer principali (in `src/`):

- **Market Data** (`market_data/`, `data_feed/`): load CSV OHLCV, freshness,
  bridge MT5 read-only, aggiornamento multi-timeframe.
- **Strategy / Lab** (`strategy/`, `strategy_lab/`): indicatori, struttura,
  segnali, famiglia V50/V51, sweep di ricerca.
- **Risk** (`risk/`): risk manager + position sizing (gate obbligatorio).
- **Backtest / Paper** (`backtesting/`, `paper/`): backtester, paper-forward,
  degradazione, defensive mode.
- **Execution** (`execution/`, `broker/`): **disabilitata di default**, demo-only
  MT5, live broker solo come interfaccia protetta.
- **AI Reasoning** (`ai_reasoning/`): **solo consulenziale / report-only**, non
  può aprire ordini.
- **Control Room** (`control_room/`): orchestratore, monitor, shadow monitor,
  telegram report.
- **Diagnostica** (`analysis/`, scripts `run_v51_*`): report su sessioni,
  rifiuti, contesto MTF, trade outcome.

Blueprint architetturale: `docs/system_architecture_blueprint.md`.

---

## 2. Obiettivo operativo

Il sistema deve aiutare a capire:

- quali segnali V51 sono realmente validi;
- quali segnali vengono rifiutati e perché;
- quali filtri bloccano troppo (e quali sono safety-critical);
- quali sessioni hanno valore statistico;
- se Asia = accumulazione/liquidità, Londra = manipolazione, New York =
  inversione/conferma;
- se i quality guard scartano segnali potenzialmente buoni (falsi negativi);
- se il bias D1/H4/H1/M15/M5/M1 è coerente con il setup;
- quando un trade può essere solo osservato, simulato o eventualmente passato a
  demo execution protetta.

Ordine di promozione di un'idea: **diagnostica → validazione statistica →
paper → demo-only gated → (eventuale) live solo con approvazione manuale
esplicita**.

---

## 3. Regole di sicurezza assolute

1. Non toccare codice di **live execution reale**.
2. Non abilitare l'**invio di ordini reali**.
3. Non modificare credenziali, broker, API key, file `.env` o configurazioni
   sensibili.
4. Non eliminare **guardrail di rischio**.
5. Non abbassare soglie operative solo per **aumentare il numero di trade**.
6. Niente refactor grandi senza motivo.
7. Prima di modificare codice, **spiega il piano**.
8. Ogni modifica deve avere **test**.
9. Ogni modifica deve mantenere verdi i comandi di validazione (sezione 5).
10. Se trovi ambiguità, **fermati e chiedi**.

### Invarianti di sicurezza già codificate (da non indebolire)

- `LIVE_MODE` resta `false` di default; `allow_real_live` resta `false`.
- `config/strategy_v51.yaml`: `demo_only: true`, `allow_real_live: false`,
  `allow_demo_execution: false`, `execution_enabled: false` (di default).
- `validate_v51_config()` impone: `risk_per_trade ≤ 0.005`,
  `1 ≤ max_trades_per_day ≤ 2`, `max_open_positions == 1`,
  `min_risk_reward ≥ 1.2`, geometria SL/TP coerente, `allow_real_live` falso.
- Ogni segnale tradabile deve avere stop loss e passare dal risk manager.
- Nessuna API key nel codice; nessun `.env` nel repo.
- `config/demo_execution.local.yaml` è un override locale VPS: **mai committare**.

Prima si **logga** la motivazione di un rifiuto, poi si valuta se un filtro è
troppo stretto. Mai il contrario.

---

## 4. Workflow corretto (Mac → GitHub → VPS)

- **Mac**: sviluppo, test, commit, push sul branch dedicato.
- **GitHub**: sincronizzazione branch (non pushare su un branch diverso da quello
  assegnato senza permesso esplicito).
- **VPS Windows** (`C:\Users\Administrator\xau_auto_trader`,
  `.venv\Scripts\python.exe`): ha MT5 installato. Un task PowerShell
  (`run_demo_cycle.ps1`) esegue `check_mt5_demo_execution_readiness.py` e poi
  `run_demo_execution_once.py --execute-demo`, loggando in
  `reports/demo_execution/demo_cycle.log`.

Dati runtime, report e `data/raw/*.csv` sono **gitignorati**: vivono solo sul
VPS. Non vanno committati né rimossi dal repo.

---

## 5. Comandi test obbligatori

Prima e dopo ogni modifica devono restare verdi **tutti** i seguenti:

```bash
python -m pytest -q
python scripts/run_v51_diagnostic_report.py
python scripts/run_v51_live_safe_cycle.py --dry-run
```

Baseline noto: `pytest` = 512 passed (nessun ordine inviato dai diagnostici;
`--dry-run` non invia ordini).

> Nota storica: una vecchia consegna citava
> `python scripts/run_v2_shadow_report.py --dry-run`. Quello script **non
> esiste** nel repo: il gate corretto sono i due comandi diagnostici sopra. Il
> concetto "shadow" reale è `src/control_room/shadow_monitor.py`, invocato via
> `scripts/run_control_room_once.py`.

---

## 6. File principali

| Area | File |
|---|---|
| Config V51 + safety gate | `config/strategy_v51.yaml` |
| Strategia V51 + validazione | `src/strategy_lab/strategy_v51_demo_intraday.py` |
| Gate esecuzione demo MT5 | `src/execution/v51_demo_executor.py` |
| Esecuzione demo MT5 (base) | `src/execution/mt5_demo_executor.py` |
| Live broker protetto | `src/execution/live_broker.py` |
| Freshness dati | `src/market_data/data_freshness.py` |
| Diagnostica V51 | `scripts/run_v51_diagnostic_report.py` |
| Tassonomia rifiuti V51 | `src/analysis/v51_rejection_taxonomy.py`, `scripts/run_v51_rejection_diagnostics.py` |
| Market structure sessioni | `src/analysis/session_structure.py`, `src/analysis/v51_structure_context.py`, `scripts/run_v51_market_structure_diagnostics.py` |
| Validazione esiti V51 | `src/analysis/v51_outcome_simulation.py`, `scripts/run_v51_outcome_diagnostics.py` |
| Quality review V51 | `src/analysis/v51_quality_review.py`, `scripts/run_v51_quality_review.py` |
| Edge lab multi-strumento | `src/analysis/session_edge_lab.py`, `scripts/run_session_edge_lab.py`, `config/edge_lab.yaml` |
| Edge NY condizionato | `src/analysis/ny_conditional_edge.py`, `scripts/run_ny_conditional_edge.py` |
| Audit test multipli | `src/analysis/multiple_testing.py`, `scripts/run_edge_significance_audit.py` |
| Anomalia overnight (teoria) | `src/analysis/overnight_anomaly.py`, `scripts/run_overnight_anomaly.py` |
| Fetch dati OHLCV (ricerca) | `scripts/fetch_yahoo_ohlcv.py` |
| Normalizza CSV broker | `scripts/normalize_broker_csv.py` |
| Export MT5 multi-simbolo (broker-time) | `scripts/export_mt5_instruments.py` |
| Research API (console web) | `src/api/research_service.py`, `src/api/app.py`, `scripts/serve_research_api.py` |
| Demo readiness (report-only) | `src/analysis/v51_demo_readiness.py`, `scripts/run_v51_demo_readiness_report.py` |
| Validazione esiti V51 | `src/analysis/v51_outcome_simulation.py`, `scripts/run_v51_outcome_diagnostics.py` |
| Ciclo demo live-safe | `scripts/run_v51_live_safe_cycle.py` |
| Contesto MTF | `scripts/run_v51_mtf_context_report.py` |
| Shadow monitor | `src/control_room/shadow_monitor.py` |
| Analisi sessioni | `src/analysis/session_analysis.py` |
| Risk | `src/risk/risk_manager.py`, `src/risk/position_sizing.py` |

> La logica di **time alignment** (UTC, candidate-in-future, stale, cooldown)
> NON è in un modulo separato: è inline in `src/execution/v51_demo_executor.py`
> (`_time_alignment_telemetry`, `_candidate_time_guard_reason`, `_utc_now`, …).
> Non esistono `src/utils/time_alignment.py` né `tests/test_time_alignment.py`.

---

## 7. Cosa NON modificare senza autorizzazione esplicita

- Qualsiasi cosa sotto `src/execution/` e `src/broker/`.
- `validate_v51_config()` e i gate `_validate_execution_gates()` /
  `_validate_mt5_demo_state()`.
- I flag di sicurezza in `config/strategy_v51.yaml` e nelle config di execution.
- Soglie di rischio (`risk_per_trade`, `max_trades_per_day`, `min_risk_reward`,
  spread/slippage caps, drawdown/daily-loss caps).
- I test di sicurezza: `test_execution_layer_disabled`, `test_demo_no_real_live`,
  `test_ai_reasoning_cannot_execute`, `test_live_broker`,
  `test_mt5_demo_executor_safety`, `test_data_update_never_executes_orders`,
  `test_demo_duplicate_order_guard`, e simili `*_no_live` / `*_safety`.

---

## 8. Standard per ogni nuova modifica

- Spiega il **piano** prima di scrivere codice; in caso di ambiguità, fermati.
- Preferisci modifiche **additive e read-only** quando possibile (nuovo report
  che legge log esistenti, non riscrittura dei gate).
- Moduli piccoli e testabili; Python semplice e leggibile; stile coerente con il
  codice circostante.
- **Test per ogni change**; non rompere test esistenti.
- Nessuna dipendenza pesante senza necessità.
- Non committare CSV generati, report, database, `.venv`, `.env`.
- Rispetta i file YAML come unica fonte dei parametri regolabili.
- Mai indebolire un filtro di rischio per forzare più trade.

---

## 9. Roadmap tecnica (3 fasi)

### FASE 1 — Diagnostica migliorata — IN CORSO
Categorizzare i segnali rifiutati distinguendo: score basso, quality guard,
sessione bloccata, Asia accumulation, London manipulation, New York reversal,
liquidity sweep, MTF non allineato, distanza da supporto/resistenza, setup
long/short non confermato. Modulo **additivo** che legge il decision log V51, non
tocca i gate.

Già disponibile (additivo, read-only):
`src/analysis/v51_rejection_taxonomy.py` + `scripts/run_v51_rejection_diagnostics.py`
→ categorizza i rifiuti (`score_low`, `quality_guard`, `session_blocked`,
`mtf_misaligned`, `rr_low`, `freshness_time`, …) con una `disposition`
(`safety_critical` / `review_candidate` / `threshold` / `informational`) e indica
il top filtro bloccante. Output in `reports/diagnostics/v51_rejection_taxonomy*`.

Market-structure context (Asia accumulation, London manipulation/sweep, NY
reversal, liquidity sweep, distance-from-level), additivo e read-only:
`src/analysis/session_structure.py` (modello sessioni allineato a `v50_session`)
+ `src/analysis/v51_structure_context.py` + `scripts/run_v51_market_structure_diagnostics.py`
→ per giorno calcola range Asia, sweep/lato/reclaim, direzione NY; per candidato
calcola `manipulation_label`, `structure_alignment` (aligned/counter/neutral) e
distanza dal livello chiave. Output in `reports/diagnostics/v51_market_structure_*`.

### FASE 2 — Validazione quantitativa — IN CORSO
Report statistici per: performance teorica per sessione e per direzione, score
minimo efficace, qualità RR, distanza dai livelli chiave, presenza/assenza di
liquidity sweep, comportamento Asia → London → New York, segnali rifiutati
meritevoli di review, falsi negativi dei quality guard.

Già disponibile (additivo, read-only, backtest/research):
`src/analysis/v51_outcome_simulation.py` + `scripts/run_v51_outcome_diagnostics.py`
→ simula l'esito teorico dei candidati (walk-forward, no lookahead, stop-first su
candela ambigua) e produce performance per sessione, per direzione e curva dello
score minimo (`win_rate`, `avg_r`, `total_r`, `expectancy`). Metriche teoriche
sull'intero decision log, non sui soli candidati live gated. Output in
`reports/diagnostics/v51_outcomes*` e `v51_performance_*`.

Quality review (qualità RR, falsi negativi dei quality guard, review dei
rifiuti), additivo e read-only: `src/analysis/v51_quality_review.py` +
`scripts/run_v51_quality_review.py` → riusa la simulazione esiti e la tassonomia
per misurare performance per bucket RR, quanti candidati bloccati da filtri
discrezionali avrebbero teoricamente vinto e quali categorie di rifiuto
meritano review (`review_flag` solo per filtri non safety-critical con
expectancy positiva e campione ≥5). Output in `reports/diagnostics/v51_quality_*`.
Un risultato positivo è un invito a rivedere un filtro, mai a indebolirlo.

### FASE 3 — Demo controllata
Solo dopo la validazione statistica: demo execution protetta con massimo rischio,
massimo numero di trade, blocchi giornalieri, blocco drawdown, blocco news,
blocco spread, fase report-only prima dell'execution. Live reale **solo** con
approvazione manuale esplicita.

Già disponibile **solo la fase report-only** (additivo, NON arma l'execution):
`src/analysis/v51_demo_readiness.py` + `scripts/run_v51_demo_readiness_report.py`
→ simula l'equity giornaliera dei candidati ACCEPTED applicando cap trade,
daily-loss lock e drawdown lock, e produce una checklist read-only dei flag di
sicurezza (`allow_real_live`, `demo_only`, `allow_demo_execution`,
`execution_enabled`, `max_open_positions`). Output in
`reports/diagnostics/v51_demo_readiness_*`. NON modifica config/flag, NON importa
codice di execution, NON invia ordini.

Hardening dell'execution demo (autorizzato, flag di abilitazione **OFF**): il
`v51_demo_executor` ha tre guardrail protettivi opt-in — news block, daily-loss
lock, drawdown lock — **disattivati di default** (config: `news_block_enabled`,
`daily_loss_lock_enabled`, `drawdown_lock_enabled`). Possono solo **bloccare** un
ordine demo, mai allentare un gate. I flag `allow_real_live`, `demo_only`,
`allow_demo_execution`, `execution_enabled` restano invariati. **Armare la demo
execution resta una decisione separata, esplicita e manuale**: i flag in
`config/strategy_v51.yaml` non vanno portati a `true` senza autorizzazione.

---

## 10. Convenzione per i report diagnostici

- Output sotto `reports/diagnostics/`, `reports/shadow/`,
  `reports/demo_execution/` (tutti **gitignorati**, generati a runtime).
- Naming coerente: `v51_<scopo>_summary.csv`, `v51_<scopo>_<dettaglio>.csv`,
  `v51_<scopo>_latest.txt`.
- Ogni report deve dichiarare lo `status`, la `reason` e — quando applicabile —
  "No orders were sent. This is diagnostics only."
- Le motivazioni di rifiuto vanno mantenute leggibili e, dove introdotto,
  affiancate da una **categoria** stabile (es. `score_low`, `quality_guard`,
  `session_blocked`, `mtf_misaligned`, `rr_low`, `setup_unconfirmed`,
  `spread_slippage`, `daily_limit`).

---

## 11. Lavorare senza rompere VPS / live / demo

- Non abilitare ordini reali, non cambiare i flag di execution.
- Non modificare gli override locali VPS (gitignorati).
- I diagnostici e i `--dry-run` non devono mai inviare ordini.
- Mantieni invariata l'interfaccia dei log/CSV consumati dal VPS (colonne
  esistenti) per non rompere il task PowerShell schedulato.
- In dubbio sull'impatto VPS/live/demo: **fermati e chiedi**.
