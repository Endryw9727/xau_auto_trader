# XAU Auto Trader

Software Python modulare per studio, backtest e paper trading su XAU/USD.

Questo progetto serve a costruire un sistema controllato per:
- caricare dati storici OHLCV
- calcolare indicatori tecnici
- generare segnali BUY / SELL / NO_TRADE
- applicare risk management
- fare backtest
- fare paper trading simulato
- salvare trade su SQLite
- visualizzare risultati in dashboard Streamlit

## Stato attuale

Funzionalità presenti:

- CSV loader OHLCV
- Indicatori tecnici: EMA, RSI, ATR, MACD, ADX
- Struttura mercato: swing high, swing low, trend, BOS, CHOCH
- Generazione segnali
- Risk manager
- Position sizing
- Backtester
- Paper broker
- Paper trading engine
- Live broker protetto
- Database SQLite
- Dashboard Streamlit
- Configurazione centralizzata da config.yaml
- Test automatici con pytest

## Sicurezza

Il live trading è bloccato.

Regole:
- LIVE_MODE=false
- nessun ordine reale viene inviato
- nessuna API key deve essere caricata su GitHub
- ogni trade deve avere stop loss
- ogni trade passa dal risk manager
- il live broker è solo una interfaccia protetta, non collegata a broker reali

## Setup ambiente

Attiva ambiente virtuale:

    source .venv/bin/activate

Installa dipendenze:

    pip install -r requirements.txt

Esegui test:

    pytest

## Generare dati finti

Solo per verificare che il software funzioni:

    python scripts/generate_fake_xauusd_data.py

Questo crea:

    data/raw/xauusd.csv

Attenzione: i dati finti non servono per valutare la profittabilità.

## Usare dati reali

Il CSV reale deve stare qui:

    data/raw/xauusd.csv

Formato richiesto:

    Date,Open,High,Low,Close,Volume
    2026-01-01 09:00:00,2350.00,2352.00,2349.50,2351.20,1000

Timeframe consigliato iniziale:

    15m

## Lanciare backtest

    python -m src.main

Output:
- reports/backtests/trades.csv
- reports/backtests/metrics.csv
- salvataggio trade su SQLite

## Lanciare paper trading simulato

    python scripts/run_paper_trading.py

Output:
- reports/paper_trading/paper_trades.csv
- salvataggio trade su SQLite

## Lanciare V51 demo live-safe

La pipeline V51 demo live-safe aggiorna prima i dati locali da MT5 in modalita
read-only, importa eventuali CSV del bridge MT5, verifica la freshness del CSV
M15 e solo se i dati sono freschi esegue la V51 in demo. Se i dati sono stale,
la strategia non viene eseguita e viene registrato `DATA_STALE`.

    python scripts/run_v51_live_safe_cycle.py --dry-run
    python scripts/run_v51_live_safe_cycle.py --execute-demo

Output:
- reports/demo_execution/v51_live_safe_cycle.log
- reports/demo_execution/v51_demo_execution_log.csv

Lo script resta demo-only: non abilita live reale e `allow_real_live` deve
restare `false`.

Il layer di esecuzione V51 normalizza i tempi a UTC prima dei gate live-safe e
scrive nel log `now_utc`, `now_local`, `candidate_time_basis` e
`time_alignment_status`. Un candidato con timestamp futuro viene rifiutato con
`candidate_time_in_future`; un candidato fuori da `live_candidate_window_minutes`
viene rifiutato con `candidate_stale`.

Prima di inviare un ordine demo, il runner confronta il prezzo atteso con
bid/ask correnti: protegge da slippage avverso con `max_slippage_points`, blocca
inseguimenti eccessivi con `max_chase_points` e, se `reprice_live_entry=true`,
usa il prezzo live per ricalcolare SL, TP e RR. Nessun ordine viene inviato se il
RR ricalcolato scende sotto `min_risk_reward` o se SL/TP non sono coerenti.

## V51 MTF Context Report

Il report MTF V51 legge solo CSV locali e produce contesto operativo
multi-timeframe per D1, H4, H1, M15, M5 e M1 quando disponibili. Non modifica
config, non riduce filtri e non invia ordini.

    python scripts/run_v51_mtf_context_report.py
    python scripts/run_v51_mtf_context_report.py --data-dir data/raw --output-dir reports/diagnostics

Output:
- reports/diagnostics/v51_mtf_context_latest.txt
- reports/diagnostics/v51_mtf_context_summary.csv

Il bias finale puo essere `LONG_BIAS`, `SHORT_BIAS`, `MIXED` o
`NO_TRADE_CONTEXT` e serve solo come supporto diagnostico per V51.

Il report include un data alignment guard: usa `data/raw/xauusd.csv` come
primary reference, verifica freshness e prezzo di ogni timeframe, marca gli
input non validi come `MISSING`, `EMPTY`, `INVALID_COLUMNS`, `STALE` o
`PRICE_MISMATCH` e li esclude dal bias finale. Se `XAUUSD_M15.csv` e vecchio
ma `data/raw/xauusd.csv` e fresco, M15 usa la primary come fallback.

## V51 MTF Directional Filter

Il ciclo live-safe puo usare il report MTF come filtro direzionale read-only.
Il filtro non genera segnali, non modifica rischio, lot size, SL o TP e puo
solo bloccare un candidato V51 gia selezionato dagli altri gate.

La pipeline e:

    python scripts/update_mt5_timeframes.py
    python scripts/run_v51_mtf_context_report.py
    python scripts/run_v51_live_safe_cycle.py --dry-run

Config opzionale in `config/strategy_v51.yaml`:

    use_mtf_context_filter: false
    require_mtf_data_ok: true
    allowed_mtf_bias_for_buy: LONG_BIAS
    allowed_mtf_bias_for_sell: SHORT_BIAS
    max_chase_points: 80
    reprice_live_entry: true

Quando `use_mtf_context_filter` e `true`, un BUY passa solo con
`LONG_BIAS` e un SELL passa solo con `SHORT_BIAS`. `MIXED`,
`NO_TRADE_CONTEXT`, bias sconosciuti o M1/M5 non OK con
`require_mtf_data_ok=true` bloccano il trade con reason
`mtf_direction_filter_blocked`. Il risultato viene scritto anche in
`reports/demo_execution/v51_demo_execution_log.csv` nelle colonne
`mtf_final_bias`, `mtf_filter_enabled`, `mtf_filter_passed` e
`mtf_filter_reason`.

## V51 Rejection Diagnostics

Report diagnostico read-only che raggruppa i segnali V51 rifiutati in categorie
stabili, cosi e immediato vedere quale filtro blocca di piu e se quel blocco e
safety-critical o una soglia regolabile da rivedere. Non modifica config, non
abbassa filtri e non invia ordini.

    python scripts/run_v51_rejection_diagnostics.py
    python scripts/run_v51_rejection_diagnostics.py --candles 400
    python scripts/run_v51_rejection_diagnostics.py --reasons-csv reports/demo_execution/v51_demo_execution_log.csv

Output:
- reports/diagnostics/v51_rejection_taxonomy.csv
- reports/diagnostics/v51_rejection_taxonomy_latest.txt

Categorie: `score_low`, `score_gap_low`, `trend_weak`, `setup_unconfirmed`,
`quality_guard`, `rr_low`, `spread_slippage`, `session_blocked`, `daily_limit`,
`mtf_misaligned`, `liquidity_sweep`, `distance_from_level`, `freshness_time`,
`duplicate`, `no_directional_score`, `accepted`, `other`. Ogni categoria ha una
`disposition`: `safety_critical`, `review_candidate`, `threshold` o
`informational`.

## V51 Market Structure Diagnostics

Report read-only che unisce i candidati V51 al market structure per sessione
(Asia accumulation, London manipulation/sweep, New York reversal). Per ogni
giorno calcola il range Asia, se la liquidita Asia e stata spazzata (sweep) e da
quale lato, se e stata reclaimata, la direzione di New York; per ogni candidato
calcola la distanza dal livello chiave piu vicino e se la direzione e allineata
o contraria allo sweep-reclaim. Non modifica config e non invia ordini.

    python scripts/run_v51_market_structure_diagnostics.py
    python scripts/run_v51_market_structure_diagnostics.py --candles 600

Output:
- reports/diagnostics/v51_market_structure_context.csv
- reports/diagnostics/v51_market_structure_summary.csv
- reports/diagnostics/v51_market_structure_latest.txt

`manipulation_label`: `no_sweep`, `sweep_not_reclaimed`,
`london_sweep_low_reclaimed` (contesto rialzista), `london_sweep_high_reclaimed`
(contesto ribassista), `london_sweep_both_reclaimed`. `structure_alignment`:
`aligned`, `counter`, `neutral`.

## V51 Outcome Diagnostics (validazione teorica)

Report read-only di validazione quantitativa: simula l'esito teorico dei
candidati V51 camminando in avanti sulle candele chiuse successive (nessun
lookahead; su candela ambigua si assume lo stop per primo, scelta conservativa)
e misura la performance per sessione, per direzione e al variare dello score
minimo. E backtest/research: non invia ordini e non modifica config.

    python scripts/run_v51_outcome_diagnostics.py
    python scripts/run_v51_outcome_diagnostics.py --candles 800 --max-horizon 32
    python scripts/run_v51_outcome_diagnostics.py --accepted-only

Output:
- reports/diagnostics/v51_outcomes.csv
- reports/diagnostics/v51_performance_by_session.csv
- reports/diagnostics/v51_performance_by_side.csv
- reports/diagnostics/v51_performance_score_curve.csv
- reports/diagnostics/v51_outcome_latest.txt

Le metriche (`win_rate`, `avg_r`, `total_r`, `expectancy`) sono teoriche e
calcolate sull'intero decision log storico, non sui soli candidati live gated:
servono come segnale di ricerca, non come metrica di produzione.

## V51 Quality Review

Report read-only di FASE 2 che misura la qualita dei candidati V51: performance
per bucket di risk/reward, falsi negativi dei quality guard (candidati bloccati
dai filtri discrezionali che in teoria avrebbero vinto) e review dei rifiuti
(quali categorie di rifiuto sarebbero state profittevoli e meritano una
revisione umana). Non modifica config e non invia ordini.

    python scripts/run_v51_quality_review.py
    python scripts/run_v51_quality_review.py --candles 800 --horizon 32

Output:
- reports/diagnostics/v51_quality_rr.csv
- reports/diagnostics/v51_quality_rejection_review.csv
- reports/diagnostics/v51_quality_false_negatives.csv
- reports/diagnostics/v51_quality_review_latest.txt

Un `review_flag` viene alzato solo per categorie non safety-critical con
expectancy teorica positiva e campione sufficiente. Le metriche sono teoriche
sull'intero decision log storico: un risultato positivo e un invito a rivedere un
filtro, mai a indebolirlo.

## V51 Demo Readiness (report-only)

Report di FASE 3 in sola lettura: la fase report-only che precede qualsiasi demo
execution. Simula come si comporterebbero i guardrail protettivi (cap trade
giornaliero, daily-loss lock, drawdown lock) sui candidati ACCEPTED e stampa una
checklist di sicurezza read-only sui flag di config. NON abilita l'execution,
NON modifica config o flag e NON invia ordini. Armare la demo resta una
decisione separata, esplicita e manuale fuori da questo report.

    python scripts/run_v51_demo_readiness_report.py
    python scripts/run_v51_demo_readiness_report.py --candles 800 --daily-loss-limit-r 2 --max-drawdown-r 4

Output:
- reports/diagnostics/v51_demo_readiness_equity.csv
- reports/diagnostics/v51_demo_readiness_checklist.csv
- reports/diagnostics/v51_demo_readiness_latest.txt

La checklist verifica che `allow_real_live=false`, `demo_only=true`,
`allow_demo_execution=false`, `execution_enabled=false` e `max_open_positions=1`.
I budget `daily_loss_limit_r` e `max_drawdown_r` sono parametri del report, non
config di rischio: servono solo a misurare l'effetto teorico dei lock.

## Multi-Instrument Session Edge Lab

Ricerca read-only di un edge di *session drift* su piu strumenti (XAUUSD, NAS100,
EURUSD, AUDUSD, GBPUSD, USDJPY, USDCAD e altri). Per ogni sessione
(Asia/London/New York) e direzione misura l'expectancy entrando all'apertura
della sessione e uscendo alla chiusura, **al netto dei costi**, e valida con uno
split out-of-sample: un edge conta solo se e significativo (|t| >= soglia, stesso
segno) **sia in-sample sia out-of-sample**. Gli strumenti senza edge robusto
vengono marcati `EXCLUDE`.

Configura strumenti, percorsi CSV e costi in `config/edge_lab.yaml` (i CSV
vivono in `data/raw/`, gitignorati: vanno messi sulla macchina con i dati).

    python scripts/run_session_edge_lab.py

Output:
- reports/diagnostics/session_edge_verdicts.csv   (KEEP / EXCLUDE per strumento)
- reports/diagnostics/session_edge_detail.csv     (per sessione e direzione)
- reports/diagnostics/session_edge_latest.txt

Il metodo open-to-close e una prima ipotesi volutamente semplice: il modulo e la
base per ipotesi piu fini (sweep-and-reverse, breakout) sullo stesso framework di
validazione. Solo ricerca: nessun ordine inviato.

Per popolare i CSV degli altri strumenti senza MT5 puoi scaricare dati intraday
pubblici da Yahoo Finance:

    python scripts/fetch_yahoo_ohlcv.py --symbols EURUSD AUDUSD GBPUSD USDJPY USDCAD NAS100 --interval 1h --range 730d

Scrive `data/raw/<symbol>.csv` (gitignorati). Attenzione: i timestamp Yahoo sono
in UTC, mentre le finestre sessione del lab sono in ora broker; i confini sessione
sono quindi approssimati. Per uso operativo, preferire l'export da MT5 sulla VPS,
allineato all'ora broker.

## V51 Demo Protective Guardrails

Il layer di esecuzione demo V51 include guardrail protettivi opt-in, tutti
**disattivati di default** (quando spenti non cambiano il comportamento). Possono
solo **bloccare** un nuovo ordine demo, mai allentare un gate esistente e mai
armare l'esecuzione. Si configurano in `config/strategy_v51.yaml`:

    news_block_enabled: false
    news_block_windows: []          # es. ["12:25-12:35", "14:00-14:15"] in UTC
    daily_loss_lock_enabled: false
    max_daily_loss_currency: 0.0    # budget di perdita giornaliera (valuta conto)
    drawdown_lock_enabled: false
    min_equity_floor: 0.0           # equity minima: sotto, blocca

- News block: blocca i nuovi ordini se l'ora UTC corrente cade in una finestra
  news configurata.
- Daily-loss lock: somma il profitto realizzato dei deal demo V51 del giorno (via
  MT5 history) e blocca se la perdita supera `max_daily_loss_currency`.
- Drawdown lock: blocca se l'equity del conto scende sotto `min_equity_floor`.

Questi guardrail non abilitano l'esecuzione: i flag `allow_real_live`,
`demo_only`, `allow_demo_execution` ed `execution_enabled` restano invariati.
Armare la demo execution resta una decisione separata, esplicita e manuale.

## MT5 Multi-Timeframe CSV Update

Lo script aggiorna in modalita read-only i CSV multi-timeframe usati dal report
MTF V51 e poi valida ogni file. Se MT5 non restituisce un timeframe, registra
`WARNING`, non crasha e lascia invariato il file precedente. Non invia ordini.

    python scripts/update_mt5_timeframes.py
    python scripts/update_mt5_timeframes.py --symbol XAUUSD-P --data-dir data/raw --timeframes M1 M5 M15 M30 H1 H4
    python scripts/update_mt5_timeframes.py --debug-mt5

Output atteso:
- data/raw/timeframes/XAUUSD_M1.csv
- data/raw/timeframes/XAUUSD_M5.csv
- data/raw/timeframes/XAUUSD_M15.csv
- data/raw/timeframes/XAUUSD_M30.csv
- data/raw/timeframes/XAUUSD_H1.csv
- data/raw/timeframes/XAUUSD_H4.csv
- reports/diagnostics/mt5_timeframe_update_latest.txt
- reports/diagnostics/mt5_timeframe_update_summary.csv

Lo script usa direttamente le costanti MT5 (`TIMEFRAME_M1`, `TIMEFRAME_M5`,
`TIMEFRAME_M15`, `TIMEFRAME_M30`, `TIMEFRAME_H1`, `TIMEFRAME_H4`) e prova in
ordine `copy_rates_from_pos`, `copy_rates_from` con datetime UTC aware e
`copy_rates_range`. La modalita `--debug-mt5` stampa lo stesso test diretto per
ogni timeframe, includendo righe restituite e `last_error`.

Troubleshooting: se M1/M5 mostrano `No candles returned` o
`WARNING_NO_MT5_CANDLES`, eseguire prima:

    python scripts/update_mt5_timeframes.py --debug-mt5

Se anche il debug diretto non restituisce righe, aprire in MT5 i grafici M1 e M5
del simbolo, caricare lo storico con il tasto Home, controllare `Max bars in
chart` nelle opzioni MT5 e poi rilanciare:

    python scripts/update_mt5_timeframes.py

Per M15, se MT5 non restituisce candele ma `data/raw/xauusd.csv` e fresco, lo
script normalizza la primary M15 verso `data/raw/timeframes/XAUUSD_M15.csv` con
status `OK_FALLBACK_PRIMARY_M15`.

## Lanciare Strategy Lab

Confronta piu strategie sullo stesso CSV, senza live trading:

    python scripts/run_strategy_lab.py
    python scripts/run_strategy_lab.py --candles 20000
    python scripts/run_strategy_lab.py --full

La modalita predefinita usa le ultime 5000 candele per iterare piu velocemente.

Strategie iniziali:
- existing_strategy
- session_filtered_strategy
- mtf_momentum_pullback_strategy
- mtf_strict_offsession_strategy
- mtf_feature_filtered_strategy
- mtf_relaxed_offasia_strategy
- v50_pine_technical_strategy
- v50_pine_mtf_strategy
- v50_proxy_balanced_candidate

Output:
- reports/strategy_lab/strategy_comparison.csv

## Lanciare V50 MTF Lab

Esegue solo la candidata V50 basata sui CSV multi-timeframe locali:

    python scripts/run_v50_mtf_lab.py

Input:
- data/raw/timeframes/XAUUSD_M5.csv
- data/raw/timeframes/XAUUSD_M15.csv
- data/raw/timeframes/XAUUSD_H1.csv
- data/raw/timeframes/XAUUSD_H4.csv

M10 viene generato da M5. I timeframe superiori vengono allineati senza
lookahead usando solo candele chiuse.

## Lanciare Feature Filter Sweep

Confronta varianti controllate della mtf_feature_filtered_strategy:

    python scripts/run_feature_filter_sweep.py
    python scripts/run_feature_filter_sweep.py --focused
    python scripts/run_feature_filter_sweep.py --relaxed --candles 20000
    python scripts/run_feature_filter_sweep.py --relaxed --full
    python scripts/run_feature_filter_sweep.py --candles 20000
    python scripts/run_feature_filter_sweep.py --full

Usa `--focused` per una griglia ridotta e piu veloce.
Usa `--relaxed` per una griglia ridotta ma piu permissiva.

Output:
- reports/strategy_lab/feature_filter_sweep.csv

## Lanciare Walk-Forward Analysis

Confronta le strategie Strategy Lab per periodo:

    python scripts/run_walk_forward_analysis.py --period yearly
    python scripts/run_walk_forward_analysis.py --period half
    python scripts/run_walk_forward_analysis.py --period quarter

Output:
- reports/strategy_lab/walk_forward_analysis.csv

La candidata `v50_pine_mtf_strategy` usa i CSV multi-timeframe locali quando
disponibili.

## Validare V50 Proxy Candidate

La candidata `v50_proxy_balanced_candidate` congela i filtri realtime-safe
derivati da `proxy_balanced_combo`. Resta solo research/backtest e non viene
promossa automaticamente.

    python scripts/run_strategy_lab.py --full
    python scripts/run_walk_forward_analysis.py --period month
    python scripts/run_walk_forward_analysis.py --period quarter
    python scripts/run_v50_stress_test.py
    python scripts/run_v50_monte_carlo.py
    python scripts/analyze_v50_proxy_candidate_selection.py

## Long-term modular architecture

La direzione architetturale di lungo periodo resta modulare e paper-first:

- Market Data Layer per XAUUSD, multi-timeframe, freshness check e futura
  qualita dati DXY/US10Y/news.
- Technical Strategy Layer per segnali, score, sessioni, SL/TP e filtri della
  strategia paper congelata.
- Macro Fundamental Layer per contesto DXY, rendimenti USA, risk sentiment e
  calendario high impact.
- AI Reasoning Layer solo consulenziale: puo spiegare, segnalare warning o
  supportare un blocco, ma non puo aprire ordini.
- Risk Engine sempre obbligatorio prima di qualsiasi decisione paper-forward.
- Paper Forward Layer per validazione locale, registro trade simulati, equity e
  status.
- Monitoring/Telegram Layer futuro solo per report e notifiche.
- Execution Layer futuro disattivato: nessun live trading, nessun broker reale,
  nessuna API key, `LIVE_MODE=false` e `allow_live=false` fino a validazione e
  approvazione manuale esplicita.

La blueprint completa e in:

    docs/system_architecture_blueprint.md

## Aprire dashboard

    streamlit run src/dashboard/dashboard.py

Poi aprire:

    http://localhost:8501

Schede dashboard:
- Backtest CSV
- Database SQLite
- Analisi Strategia
- Sicurezza Live

## Database SQLite

Percorso database:

    data/database/trading.db

Può essere aperto con DB Browser for SQLite.

Tabelle principali:
- trades
- signals
- daily_stats
- equity_curve
- errors

## Configurazione

Modifica config.yaml per cambiare parametri senza toccare codice.

Parametri principali:

    trading:
      symbol: "XAUUSD"
      live_mode: false
      base_timeframe: "15m"

    strategy:
      atr_multiplier_sl: 1.5
      atr_multiplier_tp: 3.0
      rsi_buy_max: 70.0
      rsi_sell_min: 30.0

    risk:
      risk_per_trade: 0.005
      max_risk_per_trade: 0.01
      max_daily_loss: 0.02
      max_open_trades: 2
      max_consecutive_losses: 3
      min_risk_reward: 2.0
      value_per_point: 1.0

    backtest:
      initial_balance: 1000
      commission_per_trade: 0.0
      slippage_points: 0.0
      warmup_candles: 220
      rolling_window_candles: 500

## File .env

Crea un file .env partendo da .env.example.

Esempio:

    LIVE_MODE=false
    ACCOUNT_BALANCE=1000
    RISK_PER_TRADE=0.005
    MAX_DAILY_LOSS=0.02

Non caricare mai .env su GitHub.

## Comandi Git utili

Controllare stato:

    git status

Salvare modifiche:

    git add .
    git commit -m "Descrizione modifica"

Controllare differenze:

    git diff

## Workflow consigliato

Ogni volta che lavori:

    source .venv/bin/activate
    pytest
    git status

Dopo una modifica:

    pytest
    git add .
    git commit -m "Messaggio chiaro"

## Roadmap prossima

Prossimi miglioramenti:
- import dati reali XAU/USD da broker o esportazione TradingView
- analisi per sessione London / New York
- filtro news
- migliore logica struttura mercato
- salvataggio segnali su SQLite
- report HTML
- ottimizzazione controllata parametri
- paper trading con dati reali
- eventuale broker demo
