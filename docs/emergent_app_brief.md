# Emergent App Brief — XAU Auto Trader Research Console

Brief operativo per costruire (su Emergent o qualunque builder full-stack) una
**console di ricerca** sopra il sistema quantitativo già esistente in questo
repository. È anche il **contratto API**: gli endpoint descritti qui verranno
implementati in un secondo momento come strato FastAPI sopra la pipeline.

> Regola guida: **la statistica e le decisioni sull'edge le fa il CODICE**
> (deterministico, testato). Gli LLM nell'app sono **solo consulenziali**:
> spiegano i report, propongono ipotesi, rivedono — **non** calcolano edge e
> **non** inviano ordini.

---

## 1. Scopo dell'app

Una dashboard web che permette di:

1. **Raccogliere dati** OHLCV multi-strumento (XAUUSD, NAS100, EURUSD, AUDUSD,
   GBPUSD, USDJPY, USDCAD) da MT5 (broker-time) o da fonti pubbliche.
2. **Lanciare i test di validazione** già implementati e vederne i risultati.
3. **Visualizzare i verdetti** KEEP/EXCLUDE per strumento e l'audit anti-overfitting.
4. **Assistente AI multi-modello** (Claude + GPT + Kimi) che spiega i risultati e
   propone ipotesi — in modalità report-only.

Non è un pannello di trading: non arma e non invia ordini.

---

## 2. Cosa esiste già nel repository (da NON reimplementare)

La logica è già scritta e testata (655 test verdi). L'app deve **orchestrare** e
**visualizzare** questi strumenti, non riscriverli.

### Ricerca dell'edge (research, read-only)
| Capacità | Script | Output (CSV/TXT in `reports/diagnostics/`) |
|---|---|---|
| Edge di sessione multi-strumento | `scripts/run_session_edge_lab.py` | `session_edge_verdicts.csv`, `session_edge_detail.csv` |
| Edge NY condizionato (no lookahead) | `scripts/run_ny_conditional_edge.py` | `ny_conditional_verdicts.csv`, `ny_conditional_detail.csv` |
| Anomalia overnight (ipotesi teorica) | `scripts/run_overnight_anomaly.py` | `overnight_anomaly_audit.csv` |
| **Audit test multipli (verdetto finale)** | `scripts/run_edge_significance_audit.py` | `edge_significance_audit.csv` (colonna `mtc_robust`) |

### Dati
| Capacità | Script |
|---|---|
| Export MT5 multi-simbolo (broker-time) | `scripts/export_mt5_instruments.py` |
| Fetch OHLCV pubblico (Yahoo) | `scripts/fetch_yahoo_ohlcv.py` |
| Config strumenti + costi | `config/edge_lab.yaml` |

### Diagnostica V51 (il bot)
| Capacità | Script |
|---|---|
| Tassonomia rifiuti | `scripts/run_v51_rejection_diagnostics.py` |
| Market structure sessioni | `scripts/run_v51_market_structure_diagnostics.py` |
| Validazione esiti | `scripts/run_v51_outcome_diagnostics.py` |
| Quality review | `scripts/run_v51_quality_review.py` |
| Demo readiness (report-only) | `scripts/run_v51_demo_readiness_report.py` |

---

## 3. Architettura target

```
┌──────────────── App (Emergent: frontend + backend) ───────────────┐
│ Pagine:                                                            │
│  - Data: import/export strumenti, stato dataset                   │
│  - Edge Lab: lancia scan, tabella KEEP/EXCLUDE, dettaglio         │
│  - Significance Audit: famiglia test, mtc_robust (verdetto)       │
│  - Bot Diagnostics: rifiuti, market structure, demo readiness     │
│  - AI Research: pannello multi-LLM (report-only)                  │
└───────────────┬───────────────────────────────────────────────────┘
                │ HTTP JSON
        ┌───────▼──────────────────────────────┐
        │ API layer (FastAPI) — DA IMPLEMENTARE │
        │  espone la pipeline come endpoint     │
        └───────┬──────────────────────────────┘
                │ chiamate in-process (deterministiche)
        ┌───────▼──────────────────────────────┐
        │ Codice esistente (src/analysis, ...)  │  read-only
        └────────────────────────────────────────┘
```

Persistenza app (MongoDB o equivalente): salva le **run** (timestamp, parametri,
risultati) per storicizzare gli esperimenti. NON salva chiavi/credenziali nel DB.

---

## 4. Contratto API (da implementare come FastAPI)

Tutti gli endpoint sono **read-only/research**; nessuno invia ordini. Risposte in
JSON. Errori con `{ "status": "ERROR", "reason": "..." }`.

### `GET /api/health`
→ `{ "status": "ok", "version": "...", "live_armed": false }`
(`live_armed` deve essere sempre `false`: l'app non può armare l'execution.)

### `GET /api/instruments`
Lista strumenti configurati e stato dati.
→ `{ "instruments": [ { "symbol": "XAUUSD", "csv": "data/raw/xauusd.csv",
"has_data": true, "rows": 17226, "first": "...", "last": "...",
"cost_per_trade": 0.20 } ] }`

### `POST /api/edge/session-scan`
Body: `{ "min_trades": 40, "oos_fraction": 0.30, "t_stat_threshold": 1.5 }` (tutti opzionali).
→ `{ "status": "OK", "verdicts": [ { "symbol": "...", "verdict": "KEEP|EXCLUDE",
"best_session": "...", "best_direction": "...", "best_oos_t_stat": 0.0 } ],
"detail": [ ... ] }`

### `POST /api/edge/ny-conditional`
Stesso schema; verdetti con `best_condition`, `best_direction`, `best_hypothesis`.

### `POST /api/edge/overnight`
→ leg pre-registrati con `p_value`, `bh_significant`, `mtc_robust`.

### `POST /api/edge/significance-audit`  ← **verdetto finale**
Ricalcola l'intera famiglia e applica Bonferroni + Benjamini-Hochberg.
→ `{ "status": "OK", "family_size": 68, "walk_forward_robust": 1,
"mtc_survivors": 0, "rows": [ { "symbol": "...", "source": "...", "combo": "...",
"oos_t_stat": 1.86, "p_value": 0.063, "bonferroni_significant": false,
"bh_significant": false, "mtc_robust": false } ] }`

### `GET /api/bot/rejection-taxonomy`, `GET /api/bot/market-structure`, `GET /api/bot/quality-review`, `GET /api/bot/demo-readiness`
Espongono i rispettivi report diagnostici V51 come JSON.

### `POST /api/data/fetch-yahoo`
Body: `{ "symbols": ["EURUSD", ...], "interval": "1h", "range": "730d" }`
→ stato per simbolo (rows scritte, errori). Scrive in `data/raw/` (gitignored).

> L'export MT5 (`/api/data/export-mt5`) gira solo sulla VPS con MT5: l'app lo
> espone ma deve gestire `MT5_NOT_AVAILABLE` senza errori.

---

## 5. Pannello AI Research (multi-LLM, report-only)

### Modelli e routing (non "tutti in parallelo sullo stesso compito")
- **Claude** (ragionamento/analisi): spiega i report, valuta la robustezza.
- **GPT** (alternativa/second opinion): revisione critica delle conclusioni.
- **Kimi** (long-context/costo): digerisce CSV lunghi e storiche di run.
- Routing per task: *spiegazione* → modello economico; *critica/red-team* → modello forte; *sintesi finale* → Claude.

> **Cursor NON è un modello**: è un IDE che usa questi stessi modelli. Non va
> incluso come "IA collaboratrice" nell'app.

### Regole ferree del pannello AI
1. Gli LLM ricevono **solo** i numeri già calcolati dal codice (verdetti, t-stat,
   p-value). **Non** calcolano statistiche né "trovano pattern" sui dati grezzi.
2. Output sempre etichettato come *consulenziale*. Nessuna azione automatica.
3. Un LLM non può proporre di "abbassare una soglia per far passare un edge"
   (sarebbe p-hacking) né suggerire di armare l'execution.
4. Le chiavi API stanno lato server (env var), mai nel frontend né nel DB.

### Esempio di prompt di sistema per il pannello AI
> "Sei un assistente di ricerca quantitativa. Ricevi SOLO metriche già calcolate
> (verdetti KEEP/EXCLUDE, t-stat in/out-of-sample, p-value corretti per test
> multipli). Spiega cosa significano, evidenzia i rischi di overfitting, proponi
> ipotesi con un razionale strutturale. NON inventare numeri, NON suggerire di
> abbassare soglie per ottenere un edge, NON proporre di inviare ordini. Se un
> edge non è `mtc_robust`, va trattato come non valido."

---

## 6. Vincoli di sicurezza assoluti (non negoziabili)

1. L'app è **research/diagnostica**: non invia ordini, non arma la demo, non
   tocca `src/execution/` né i flag in `config/strategy_v51.yaml`.
2. `allow_real_live` resta `false`; nessuna funzione dell'app può cambiarlo.
3. Chiavi API LLM e credenziali broker: **solo** env var lato server; mai nel
   repo, nel frontend o nel DB.
4. I dati grezzi e i report sono gitignorati: l'app li tratta come runtime.
5. Gli LLM sono report-only (coerente con `src/ai_reasoning`, che non esegue).

---

## 7. Prompt pronto da incollare in Emergent

> Costruisci una web app full-stack "Research Console" per un sistema di ricerca
> quantitativa sul trading (read-only, nessun ordine reale). Backend Python che
> espone gli endpoint REST descritti nella sezione 4 di questo brief, chiamando
> moduli Python esistenti (cartella `src/analysis`). Frontend con 5 pagine: Data,
> Edge Lab, Significance Audit, Bot Diagnostics, AI Research. La pagina
> Significance Audit è il verdetto principale: mostra la tabella con colonna
> `mtc_robust` evidenziata. La pagina AI Research collega più LLM (Claude, GPT,
> Kimi) con routing per task e modalità **report-only**: i modelli ricevono solo
> metriche già calcolate, spiegano e propongono ipotesi, non calcolano statistiche
> e non possono inviare ordini. Le chiavi API stanno in env var lato server.
> Persisti le run (parametri + risultati) in MongoDB. Vincolo assoluto: l'app non
> può armare l'esecuzione né impostare `allow_real_live=true`.

---

## 8. Ordine di lavoro consigliato

1. **Questo brief** (fatto): visione + contratto API condivisi.
2. **Strato API FastAPI** nel repo (additivo, testato, read-only) che implementa
   la sezione 4.
3. **App su Emergent** che consuma quegli endpoint (sezione 7).
4. **Pannello AI** con routing multi-LLM, report-only (sezione 5).

Niente di tutto ciò modifica i guardrail o l'execution del bot.
