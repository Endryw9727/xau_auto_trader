# Audit tecnico Kimi V2 - XAU Auto Trader V2

Data audit: 2026-06-02  
Percorso audit: `/Users/endryw/Downloads/xau_auto_trader_v2`  
Ambiente verificato: `.venv/bin/python` = Python 3.13.13  
Vincoli rispettati: nessun merge nella V1, nessuna modifica alla V1, nessuna modifica VPS, nessun branch `main` toccato. La directory V2 non risulta essere un repository git locale.

## Executive summary

La V2 ora installa correttamente e la suite passa: `.venv/bin/python -m pytest -q` restituisce `137 passed in 1.68s`; anche `.venv/bin/python -m compileall -q src tests scripts` passa senza errori.

Questo pero non significa che la V2 sia pronta per sostituire o contaminare la V1 in VPS. La V2 e oggi una piattaforma di ricerca modulare: molte parti sono funzionanti in isolamento, alcune sono integrate nel paper engine, poche sono integrate nel backtester principale, e diversi layer dichiarati "enterprise" sono ancora scaffold, demo o wrapper non collegati a un ciclo operativo realistico.

La raccomandazione principale e conservativa: non copiare la V2 in blocco nella V1. Copiare solo moduli piccoli, verificabili e read-only, con test causali e shadow mode. Non copiare broker live, paper daemon, dashboard/deploy, ML decisionale o smart money come filtro live finche non vengono corretti i rischi di integrazione, lookahead e operativita.

## Stato verificato

Comandi eseguiti:

```bash
.venv/bin/python --version
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q src tests scripts
.venv/bin/python -m pytest --collect-only -q
```

Risultati:

- Python: `Python 3.13.13`
- Test: `137 passed in 1.68s`
- Compileall: nessun syntax error
- Test raccolti: 137
- Dati live/storici in repo: nessun file sotto `data/` rilevato durante l'audit
- Report generati in repo: nessun file sotto `reports/` rilevato durante l'audit

## Architettura generale

La V2 e organizzata bene come struttura di cartelle:

- `src/strategy`: indicatori, regole, segnali base, segnali V2 con SMC, market structure
- `src/backtesting`: backtester e metriche
- `src/risk`: risk manager trade-level, position sizing, portfolio risk, cross-asset correlation
- `src/macro`: fetcher Yahoo Finance e scoring macro
- `src/news`: mock calendar, scraper ForexFactory/Investing, filtro news
- `src/ai_reasoning`: context builder, score composer, explanation, warnings
- `src/ml`: feature extraction, predictor, regime detector, trainer continuo
- `src/paper`: paper trading engine V2
- `src/broker`: SafetyGate, OANDA, IG, IB, demo broker
- `src/market_data` e `src/data_feed`: registry multi-asset, CSV loader, WebSocket/Yahoo fallback
- `src/dashboard`, `docker-compose.yml`, `k8s`, `terraform`: interfaccia e deploy

Il problema non e la struttura, ma l'accoppiamento reale. `src.main` usa ancora `data/raw/xauusd.csv`, genera segnali con `src.strategy.signals.generate_signals` e non con `generate_signals_v2`, quindi il backtest principale non usa SMC, macro filter, news filter o AI per accettare/rifiutare trade storici. Il paper engine V2 invece prova a integrare SMC, macro, news, AI e risk, ma resta paper-only e ha limiti operativi importanti.

## Moduli realmente funzionanti

Questi moduli sono utilizzabili come base tecnica o research, con review prima di qualunque import nella V1:

- `src/settings.py` e `config.yaml`: loader pulito, `LIVE_MODE=false` di default, override env per saldo/rischio/live mode.
- `src/strategy/indicators.py`: EMA, RSI, ATR, MACD, ADX pandas-only; buoni per test comparativi con V1.
- `src/strategy/rules.py`: regole leggibili per bias EMA20/EMA50, ADX, RSI, ATR SL/TP e R:R.
- `src/strategy/signals.py`: genera BUY/SELL/NO_TRADE con entry, stop loss, take profit e reason; non esegue ordini.
- `src/strategy/signals_v2.py`: aggiunge SMC score/confluence, ma non e usato dal backtester principale.
- `src/risk/position_sizing.py` e `src/risk/risk_manager.py`: sizing e blocchi trade-level funzionanti nei casi base.
- `src/risk/portfolio_risk.py`: portfolio heat, asset class concentration, drawdown approssimato, warning su correlazione.
- `src/macro/macro_engine.py`: aggrega DXY, US10Y, VIX, SPX e fornisce blocco direzionale via `should_block_side`.
- `src/news/news_filter.py`: blocca intorno a eventi mock o scraper, con finestra before/after.
- `src/ai_reasoning/*`: score e warning deterministici, non LLM; buoni come spiegatore/reporting.
- `src/ml/*`: feature extraction, heuristic/sklearn predictor, persistence e retraining trigger funzionano nei test.
- `src/derivatives/*`: Black-Scholes, Greeks, futures calendar e contango/backwardation sono moduli research validi.
- `src/market_data/asset_registry.py`: registry multi-asset completo per XAU, EUR, GBP, BTC, JPY.
- `src/data_feed/market_data.py`: CSV loader, resampling, freshness check.
- `src/monitoring/cloud_monitoring.py`: metriche JSONL e formato Prometheus base.

## Moduli scaffold o placeholder

Restano placeholder espliciti:

- `src/execution/execution.py`
- `src/paper/paper.py`
- `src/control_room/control_room.py`
- `src/database/db.py`
- `src/database/models.py`
- `src/features/features.py`
- `src/lab/lab.py`
- `src/strategy_lab/strategy_lab.py`
- `src/dashboard/dashboard.py`
- `src/monitoring/monitoring.py`
- `src/market_data/market_data.py`
- `scripts/run_paper_trading.py`
- `scripts/run_v51_live_safe_cycle.py`
- `scripts/update_mt5_timeframes.py`
- `scripts/run_v51_mtf_context_report.py`

Parziali o demo:

- `src/data_feed/websocket_client.py`: Yahoo fallback funziona come polling REST; OANDA e Polygon sono `TODO/pass`.
- `scripts/run_ai_analysis.py`: demo report-only.
- `scripts/run_ml_predictor.py`: usa mock trades se mancano report reali.
- `scripts/run_walk_forward_ai.py`: research script, non produzione.
- `src/dashboard/dashboard_v2.py`: dashboard ampia, ma legge report/file locali e avvia analisi live Yahoo; non e controllo operativo.

## Qualita dei test

Punti forti:

- 137 test passano.
- Testano import, configurazione, dataclass, safety gate base, indicatori, SMC, macro mock, news mock, ML, portfolio risk, derivatives, websocket lifecycle.
- Gli integration test verificano che molti componenti possano essere istanziati insieme.

Limiti importanti:

- `tests/test_backtester.py` copre solo DataFrame vuoto. Non valida PnL, skip fino a exit, commissioni, slippage, max daily loss, sessioni, overlapping trades o ordine SL/TP nella stessa candela.
- `tests/test_signals.py` copre solo input vuoto/insufficiente. Non valida la qualita dei segnali base su dataset causali.
- `tests/test_signals_v2.py` controlla colonne SMC, non accuratezza della confluence ne blocco con `min_smc_score`.
- Molti test sono smoke test: `assert isinstance`, `assert len(events) >= 0`, `assert result.allowed in {True, False}`.
- Macro nei test e sempre mockata; non c'e test di fallback reale Yahoo, timeout o dati mancanti.
- News calendar reale non viene testato con HTML fixtures robuste; gli scraper possono rompersi se cambiano i siti.
- Broker reali non sono testati con mock HTTP serio; il SafetyGate e testato, ma non l'intero flusso order payload + audit log + daily risk.
- Nessun test copre `PaperTradingEngineV2.run_cycle` con trade eseguito e successiva chiusura.
- Nessun test di non-regressione specifico per lookahead/repainting.

Conclusione sui test: buoni per dire "il codice importa e le API base sono coerenti"; insufficienti per dire "il sistema e tradabile".

## Safety live trading

Guardrail positivi:

- `config.yaml` e `.env.example` hanno `LIVE_MODE=false`.
- `SafetyGate.check_can_trade()` blocca se `LIVE_MODE` non e esplicitamente true.
- Richiede `.LIVE_TRADING_APPROVED` di default.
- Richiede simboli approvati, max trade per giorno e max risk per giorno.
- Logga tentativi in `reports/safety/real_trading_attempts.log`.
- AI, ML e Telegram non hanno codice che invii ordini direttamente.

Criticita:

- I client OANDA/IG/IB chiamano `check_can_trade(order.symbol, order.units)`: il secondo parametro e chiamato `risk_amount`, ma viene passato `units`. Questo rende il daily risk gate semanticamente errato.
- I client registrano `record_trade_attempt(..., risk=0.0)` e `register_executed_trade(0.0)`, quindi il consumo di rischio giornaliero live non cresce davvero.
- `close_position`, `modify_position`, `cancel_order` non passano dal SafetyGate e non loggano nello stesso audit log. Chiudere una posizione riduce rischio, ma modifiche SL/TP e cancel possono aumentare rischio operativo e meritano audit.
- `SafetyGate.generate_approval_file()` puo generare un file approvato senza workflow interattivo nel codice. Non e pericoloso finche non viene invocato, ma in V1 non va importato come comando semplice.
- `SafetyApproval.session_hash` viene caricato ma non validato rispetto alla sessione corrente.
- Il gate non verifica esplicitamente che ogni ordine live abbia stop loss. Questa garanzia oggi sta altrove, non nel gate finale.

Giudizio: i guardrail non sono permissivi di default, ma il SafetyGate non e ancora sufficiente come ultimo baluardo live istituzionale.

## Broker safety gate

OANDA, IG e IB hanno un pattern coerente: `paper_mode=True` di default e SafetyGate solo quando `paper_mode=False`. Questo e corretto come principio.

Problemi per uso reale:

- Risk amount sbagliato, come sopra.
- OANDA usa payload semplificati e mapping ordine non pienamente aderente alle specifiche broker.
- IG usa payload semplificati; close via `DELETE` con JSON puo essere fragile.
- IB richiede `ib_insync`; la dependency non e pinning stretto e il contratto XAUUSD e forzato a future GC `202512`.
- OCO/Bracket sono builder o implementazioni semplificate, non una gestione robusta di lifecycle, fill parziali, cancel sibling, reconciliation e retry.
- Nessuna integrazione broker reale e chiamata da `src.main` o dal paper engine V2.

Raccomandazione: non copiare nessun client broker V2 nella V1 live. Al massimo copiare idee di interfaccia e testare un SafetyGate piu forte davanti ai broker gia esistenti in V1.

## Risk manager

Trade-level risk manager:

- Controlla max open trades, max consecutive losses, daily loss, min R:R, position sizing, max risk per trade.
- Usa balance corrente e stop distance.
- E semplice e leggibile.

Limiti:

- Non resetta automaticamente daily stats per data; serve chiamata esterna.
- Non conosce portfolio risk manager.
- Non conosce spread, slippage, margine, leverage, min/max lot broker.
- Non blocca simboli non permessi; quello e nel SafetyGate.
- Nel backtester viene usato in modo non realistico perche i trade vengono aperti, simulati nel futuro e chiusi nello stesso loop logico; quindi `max_open_trades` non rappresenta bene sovrapposizioni temporali.

Portfolio risk:

- Buona base per heat e asset class concentration.
- Correlation exposure oggi produce warning, non blocco.
- Drawdown e calcolato su unrealized PnL con approssimazione `peak_equity = equity - total_pnl`.
- Non e integrato in `run_backtest`, `generate_signals`, `src.main` o nei broker reali.

## Backtester

Il backtester e utile come prototipo, non ancora come strumento di ricerca affidabile.

Funziona:

- Genera segnali base.
- Usa RiskManager per sizing.
- Simula SL/TP sulle candele future.
- Esporta trades/metrics CSV.

Criticita:

- Usa `generate_signals`, non `generate_signals_v2`; quindi SMC/macro/news/AI non influenzano il backtest principale.
- Apre un trade su una candela, cerca l'exit su tutto il futuro, poi torna alla candela successiva invece di saltare fino all'exit. Questo consente trade sovrapposti non rappresentati correttamente.
- `max_open_trades` e quasi neutralizzato perche il trade viene chiuso logicamente dentro la stessa iterazione.
- Non gestisce realisticamente "SL e TP nella stessa candela"; controlla prima lo stop e poi il target, quindi introduce una convenzione pessimistica non configurabile.
- Entry a close della candela del segnale: accettabile solo se il segnale viene confermato a candle close e l'esecuzione avviene next bar o con slippage modellato. Oggi non c'e next-bar fill esplicito.
- Non usa spread dinamico, session spread, broker constraints o partial fill.
- Test quasi assente.

Non va usato per decidere performance reale della V2 o per ottimizzare parametri da mettere in V1.

## AI reasoning

La "AI reasoning" non e AI generativa e non usa LLM: e uno scoring deterministico con spiegazioni testuali.

Punti utili:

- Buon context builder per report: technical, macro, news, session, risk.
- Score composer con pesi configurabili.
- Warning system con blocchi su news/risk/R:R.
- Non esegue ordini.

Limiti:

- `min_confidence_for_trade` in config non e usato come blocco operativo esplicito nel paper engine.
- `AIReasoningGuardrails` esiste ma non e integrato nel paper engine o nel main.
- In `src.main`, l'AI viene calcolata solo sull'ultimo segnale e non influenza il backtest.
- Nel paper engine, l'AI blocca solo se i warning hanno action `BLOCK`, non in base a raccomandazione debole o confidence sotto soglia.
- Le spiegazioni possono dare un senso di autorevolezza maggiore della reale validazione quantitativa.

Da copiare in V1 solo come report/explanation layer, mai come esecutore o filtro live prima di test shadow.

## Macro layer

Funziona come modulo:

- Fetch DXY, US10Y, VIX, SPX via Yahoo Finance.
- Calcola bias EMA fast/slow e score composito.
- Calcola correlazione XAU/DXY se riceve dati XAU allineati.
- `should_block_side()` puo bloccare BUY/SELL contrari alla macro.

Limiti:

- `src.main` crea `MacroEngine()` senza passare `settings.macro`; quindi pesi/soglie/simboli configurati in `config.yaml` non sono pienamente applicati.
- `MacroEngine.analyze()` restituisce sempre `block_trade=False`; il blocco e disponibile solo chiamando `should_block_side()`.
- Nel backtester macro non blocca trade.
- Nel paper engine macro puo bloccare, ma solo sul ciclo corrente e con dati Yahoo recenti, non su calendario storico.
- I fetcher usano simboli hardcoded (`DX-Y.NYB`, `^TNX`, `^VIX`, `^GSPC`) invece di usare sempre la config.
- Yahoo Finance e una sorgente fragile per produzione live.

Da copiare: scoring macro come advisory/read-only. Non copiare come filtro live finche non e configurato, testato e backtestato causalmente.

## News/calendar layer

Funziona:

- `CalendarAPI` supporta backend `mock`, `forex_factory`, `investing`.
- `NewsFilter` blocca una finestra attorno agli eventi.
- Scraper con BeautifulSoup e headers custom.

Limiti:

- `calendar_fetcher.fetch_economic_calendar()` usa sempre `CalendarAPI(backend="mock")`.
- `NewsFilter` usa il calendario di oggi/now; non e adatto a backtest storico.
- Il mock usa generazione deterministica solo in modo debole; i test accettano anche lista vuota.
- Scraper reali non sono testati con fixture HTML e possono rompersi facilmente.
- Timezone e orari evento non sono normalizzati in modo istituzionale.
- Non c'e caching robusto, retry policy, provider fallback verificato o deduplica seria.

Da copiare nella V1 solo come "avoid news" informativo o shadow. Non usarlo per bloccare live senza provider affidabile e test su eventi reali.

## Smart Money Concepts

FVG:

- Implementazione semplice: bullish FVG se `Low[i] > High[i-2]`, bearish se `High[i] < Low[i-2]`.
- Causale se usata a candle close.
- Non gestisce mitigazione/fill del gap, estensione zona, invalidazione o timeframe superiore.

Order blocks:

- Identifica candela contraria seguita da movimento impulsivo.
- Usa la candela successiva per confermare l'OB. Questo e accettabile solo se l'OB viene usato dopo la chiusura della candela di conferma.
- Non gestisce breaker block, mitigazione, volume, struttura o BOS reale.

Liquidity:

- Usa `next_close` per confermare sweep. Quindi una sweep su candela `i` e nota solo dopo `i+1`.
- In `generate_signals_v2`, la funzione riceve dati fino alla candela corrente, quindi puo confermare sweep della candela precedente. Questo e ragionevole se l'entry e dopo la candela corrente; meno se si considera entry alla close corrente senza slippage.

Analyzer:

- Conta segnali bullish/bearish e produce bias.
- Non e una strategia SMC istituzionale, ma un confluence score euristico.

Da copiare nella V1 solo come overlay/report o filtro shadow, non come condizione live finche non sono risolti mitigazione, causalita e validazione multi-timeframe.

## Lookahead bias e repainting

Rischi identificati:

- `detect_swing_highs/lows` usa candele a destra. Questo repainta per definizione: uno swing e noto solo dopo `window` candele. `analyze_structure()` usa questi swing e quindi non va usato come feature di ingresso immediata senza lag.
- `detect_bos()` usa swing calcolati con right-window; puo incorporare informazione futura se applicato sull'intera serie storica.
- `detect_order_blocks()` usa `next_candle` per confermare. Serve lag operativo esplicito.
- `detect_liquidity_sweeps()` usa `next_close`. Serve lag operativo esplicito.
- Il backtester simula trade guardando tutto il futuro e poi riprende dalla candela successiva, creando sovrapposizioni temporali non realistiche.
- Entry a close del segnale senza next-bar execution puo essere troppo ottimistica in live.
- News e macro non sono storicizzati nel backtester; quindi non c'e validazione causale di quei filtri.

Regola per integrazione V1: ogni feature SMC/structure deve avere una colonna `available_at` o essere shiftata del numero di candele necessario prima di poter influenzare un trade.

## Overfitting

Rischi:

- Strategy lab ha profili predefiniti e walk-forward semplice, ma non ottimizza davvero su performance out-of-sample robusta.
- ML predictor usa RandomForest con split casuale (`train_test_split`) e non time-series split. Per trading questo puo sovrastimare accuracy.
- Le metriche del backtester non sono affidabili abbastanza per addestrare modelli.
- Gli script demo possono generare mock trades e mostrare accuracy non collegata al mercato reale.
- Nessuna purged cross-validation, embargo, nested walk-forward o controllo multiple-testing.

Regola per V1: ML solo advisory in shadow mode. Nessun blocco/allow live basato su ML finche non c'e dataset reale V1, split temporale, metriche out-of-sample e audit leakage.

## Integrazione reale nel signal generation

Stato attuale:

- `src.strategy.signals.generate_signals`: usato dal backtester e da `src.main`; solo tecnico.
- `src.strategy.signals_v2.generate_signals_v2`: usato da paper engine, demo AI, dashboard; include SMC ma non macro/news/AI.
- Macro/news/AI sono filtri nel `PaperTradingEngineV2.run_cycle`, non nel signal generator.
- Portfolio risk non e agganciato al paper engine, al backtester principale o ai broker.
- Multi-asset registry non guida `src.main`, che resta XAUUSD/file statico.

Quindi la V2 non ha ancora un "decision pipeline" unico e verificabile. Ha piu pipeline parallele:

- backtest tecnico base
- demo AI con ultimo segnale
- paper engine V2 con SMC/macro/news/AI/risk
- dashboard che ricompone analisi in modo interattivo

Prima di copiare qualcosa in V1, serve un unico contratto: `SignalCandidate -> RiskCheck -> PortfolioRiskCheck -> ExecutionDecision`, con input causali e log completo.

## Paper trading V2

Punti positivi:

- Integra SMC, macro, news, AI warning, risk manager e demo guardrails.
- Non usa broker reali.
- Richiede stop loss via demo guardrails.

Criticita:

- `check_data_freshness` rifiuta CSV storici se non aggiornati entro 30 minuti; il WebSocket Yahoo fallback viene avviato dallo script continuo ma non aggiorna il DataFrame usato dal ciclo.
- `DemoBrokerReadOnly.place_order()` crea ordini ma non crea posizioni.
- Il paper engine registra open trades nel RiskManager ma non ha una gestione completa di chiusura SL/TP; dopo pochi trade puo bloccarsi su max open trades.
- `LivePaperTradingEngine` esiste in `websocket_client.py`, ma non e integrato con `PaperTradingEngineV2`.
- Non salva automaticamente i paper trades nel DB; importa `save_trades_dataframe_to_db` ma non lo usa nel ciclo.

Giudizio: utile come prototipo di orchestrazione; non ancora affidabile come daemon paper continuo.

## Differenze rispetto alla V1 su VPS

Non ho ispezionato ne toccato la V1 o il VPS. Il confronto sotto e quindi operativo/architetturale, basato su cio che si vede nella V2 e sul fatto che la V1 gira su VPS.

Differenza chiave:

- V1 su VPS: presumibilmente sistema operativo reale, con routine gia compatibili con ambiente live/paper, dati effettivi e scheduling esistente.
- V2: research platform modulare, installabile e testata, ma con molte integrazioni demo/scaffold e nessuna prova reale su dati/ordini V1.

Differenze pratiche:

- V2 e piu ampia: macro, news, AI reasoning, SMC, ML, multi-asset, derivatives, dashboard, cloud deploy.
- V2 e meno provata operativamente: non ha dati nel repo, non ha report correnti, non ha un ciclo live-safe reale V51, non aggiorna MT5 timeframe.
- V2 ha piu guardrail dichiarati, ma i broker live non sono pronti per produzione.
- V2 ha test verdi, ma molti test sono smoke/unit; la V1 su VPS probabilmente ha valore empirico superiore per stabilita runtime.
- V2 usa Yahoo/mock/scraper per vari layer; V1 puo avere feed MT5/VPS piu concreti.

Conclusione: la V2 deve essere trattata come laboratorio da cui estrarre componenti, non come upgrade diretto.

## Cosa vale la pena copiare nella V1

Priorita alta, se compatibile e testato:

- Safety mindset e formato audit log per tentativi reali, ma correggendo risk amount, session hash, stop-loss mandatory e logging di modify/cancel.
- `settings.py`/config ideas, solo se non rompe config V1.
- `position_sizing.py` e parti di `risk_manager.py`, confrontate con risk V1.
- Indicatori core come libreria testata, se i valori combaciano con V1/MT5.
- `market_data.load_csv_data`, resampling e freshness check, adattati ai file V1.
- `ai_reasoning` come report-only explanation layer.
- Macro score come advisory read-only in dashboard/report.
- News filter solo come warning shadow.
- Smart money solo come overlay diagnostico o score shadow.
- Portfolio heat come report e poi blocco separato, dopo integrazione con posizioni reali V1.

## Cosa NON va copiato nella V1

Non copiare:

- OANDA/IG/IB live clients come esecuzione reale.
- `SafetyGate.generate_approval_file()` come workflow semplice di produzione.
- `run_backtest` come metrica di performance affidabile.
- `PaperTradingEngineV2` come daemon operativo.
- `WebSocketDataFeed` per OANDA/Polygon, perche sono placeholder.
- `scripts/run_v51_live_safe_cycle.py`, `update_mt5_timeframes.py`, `run_v51_mtf_context_report.py`, perche sono placeholder.
- `dashboard_v2.py` come control room live.
- ML predictor per bloccare/approvare trade live.
- SMC/structure come filtro live senza lag/causalita.
- Docker/K8s come produzione VPS senza revisione: compose ha servizi demo e il "db" e solo volume alpine, non un database reale condiviso.

## Piano di integrazione controllata

### Sprint 1 - Auditabile, read-only, zero execution

Obiettivo: copiare solo componenti che non possono eseguire ordini.

Task:

- Creare in V1 un namespace separato, ad esempio `v2_shadow/`, senza cambiare il ciclo live.
- Importare indicatori core e confrontare output con indicatori V1/MT5 su 2-3 dataset storici.
- Importare explanation AI come report-only, senza blocco trade.
- Importare macro advisory come report-only, con config esplicita e fallback se Yahoo fallisce.
- Importare news warning come report-only, non blocco.
- Aggiungere test causali per indicatori e signal candidate.
- Aggiungere log shadow: cosa avrebbe detto V2 mentre V1 continua invariata.

Exit criteria:

- Nessun cambio a execution V1.
- Nessun cambio a broker V1.
- Report shadow per almeno 1-2 settimane di runtime VPS/paper.
- Test V1 invariati verdi.

### Sprint 2 - Risk e safety hardening, ancora no auto-trade V2

Obiettivo: usare la V2 per rafforzare guardrail, non per generare trade.

Task:

- Portare un SafetyGate rafforzato: `LIVE_MODE`, approval file, allowed symbols, stop-loss mandatory, daily risk amount reale, daily trade count, session hash validato.
- Loggare place/modify/cancel/close in audit log, con distinzione reduce-risk/increase-risk.
- Integrare portfolio heat in modalita warning e poi blocco configurabile.
- Aggiungere test broker con mock HTTP/API: gate block, approved order, missing SL, symbol non ammesso, daily risk consumed.
- Aggiungere reset daily basato su data/sessione.
- Introdurre un contratto unico `ExecutionDecision` prima del broker.

Exit criteria:

- La V1 e piu sicura anche senza usare segnali V2.
- Safety tests coprono broker flow end-to-end.
- Nessun ordine reale puo partire senza SL, risk amount e audit log.

### Sprint 3 - Signal confluence in shadow, poi micro rollout

Obiettivo: valutare SMC/macro/news/AI come filtri, non sostituire la strategia.

Task:

- Costruire pipeline causale unica: `SignalCandidate -> SMC lagged -> Macro historical/current -> News calendar -> AI explanation -> Risk -> Portfolio`.
- Correggere backtester: next-bar execution, skip fino a exit, overlapping controllato, spread/slippage, session timezone, SL/TP same candle policy configurabile.
- Aggiungere colonne `available_at` o `shift()` per structure/sweep/order block.
- Backtest out-of-sample su dati V1 reali, senza ML decisionale.
- Shadow mode VPS: registrare quando V2 avrebbe bloccato/permesso rispetto alla V1.
- Solo dopo evidenza, abilitare un filtro alla volta in paper/demo: prima news hard block, poi macro directional block, poi SMC threshold.

Exit criteria:

- Nessun filtro V2 live senza almeno N trade shadow e report drawdown/opportunity cost.
- Rollback immediato via config.
- V1 default behavior invariato quando i flag V2 sono off.

## Verdetto finale

La V2 e migliorata molto rispetto al vecchio stato: installa, compila e passa 137 test. Il valore principale e architetturale e didattico: offre moduli piccoli e separabili per indicatori, report AI, macro/news advisory, SMC overlay, risk ideas e dashboard.

Non e pero una V2 enterprise pronta per live execution. Le aree decisive - backtesting causale, broker safety reale, portfolio risk integrato, paper trading lifecycle, storico macro/news, ML out-of-sample - richiedono ancora lavoro prima di qualunque integrazione con la V1 che gira su VPS.

Decisione consigliata: cherry-pick controllato, read-only prima, safety hardening poi, signal filters solo in shadow mode e con rollback totale.
