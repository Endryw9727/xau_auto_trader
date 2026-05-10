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

Output:
- reports/strategy_lab/strategy_comparison.csv

## Lanciare Feature Filter Sweep

Confronta varianti controllate della mtf_feature_filtered_strategy:

    python scripts/run_feature_filter_sweep.py
    python scripts/run_feature_filter_sweep.py --focused
    python scripts/run_feature_filter_sweep.py --candles 20000
    python scripts/run_feature_filter_sweep.py --full

Usa `--focused` per una griglia ridotta e piu veloce.

Output:
- reports/strategy_lab/feature_filter_sweep.csv

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
