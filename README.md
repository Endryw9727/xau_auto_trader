# XAU Auto Trader V2 — Enterprise Trading System

Sistema modulare enterprise-grade per trading research, backtest, paper trading, analisi AI/ML su multi-asset con deploy cloud-native.

## 🏗️ Architettura Completa

```
┌─────────────────────────────────────────────────────────────────────┐
│  DATA LAYER         │  CSV, MT5 Bridge, WebSocket, Yahoo Finance   │
├─────────────────────────────────────────────────────────────────────┤
│  TECHNICAL LAYER    │  EMA, RSI, ATR, MACD, ADX, Structure       │
│                     │  Signals V2 + Smart Money Confluence         │
├─────────────────────────────────────────────────────────────────────┤
│  SMART MONEY        │  FVG, Order Blocks, Liquidity Sweeps         │
├─────────────────────────────────────────────────────────────────────┤
│  MACRO LAYER        │  DXY, US10Y, VIX, SPX500                    │
│                     │  Correlation Analyzer                        │
├─────────────────────────────────────────────────────────────────────┤
│  NEWS LAYER         │  ForexFactory Scraper, Investing.com Scraper │
│                     │  Event Impact Scorer                         │
├─────────────────────────────────────────────────────────────────────┤
│  AI REASONING       │  Context Builder, Score Composer             │
│                     │  Explanation Engine, Warning System            │
├─────────────────────────────────────────────────────────────────────┤
│  ML LAYER           │  Trade Features, Predictor                 │
│                     │  Regime Detector, Continuous Trainer         │
│                     │  Model Persistence, Drift Detection            │
├─────────────────────────────────────────────────────────────────────┤
│  MULTI-ASSET        │  XAU, EUR, GBP, BTC, JPY                     │
│                     │  Asset-Specific Strategy Config                │
├─────────────────────────────────────────────────────────────────────┤
│  STRATEGY LAB       │  Strategy Selector per Regime                │
│                     │  Walk-Forward Analysis                       │
├─────────────────────────────────────────────────────────────────────┤
│  ADVANCED ORDERS    │  Trailing Stop, OCO, Bracket Orders          │
│                     │  Scale-In/Out, Time-Based Expiry             │
├─────────────────────────────────────────────────────────────────────┤
│  PORTFOLIO RISK     │  Portfolio Heat, Cross-Asset Correlation     │
│                     │  Asset Class Limits, Diversification Score     │
├─────────────────────────────────────────────────────────────────────┤
│  DERIVATIVES        │  Black-Scholes Options (Greeks)              │
│                     │  Futures Calendar, Contango/Backwardation      │
├─────────────────────────────────────────────────────────────────────┤
│  BROKER INTEGRATION │  OANDA, IG, Interactive Brokers              │
│                     │  Safety Gate (mandatory approval)              │
├─────────────────────────────────────────────────────────────────────┤
│  RISK ENGINE        │  Position Sizing, Max DD, Consec Losses       │
├─────────────────────────────────────────────────────────────────────┤
│  EXECUTION          │  Paper Trading V2, Live Paper Engine         │
│                     │  Demo Broker, Real Broker (gated)              │
├─────────────────────────────────────────────────────────────────────┤
│  NOTIFICATIONS      │  Telegram Bot (5 types)                      │
├─────────────────────────────────────────────────────────────────────┤
│  MONITORING         │  Streamlit Dashboard (11 tabs)               │
│                     │  Prometheus Metrics, CloudWatch                │
├─────────────────────────────────────────────────────────────────────┤
│  DEPLOYMENT         │  Docker, Docker Compose                    │
│                     │  Kubernetes (EKS), Terraform (AWS)             │
└─────────────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

```bash
# 1. Setup
cd xau_auto_trader_v2
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# 2. Test
pytest

# 3. Demo
python scripts/run_ai_analysis.py
python scripts/run_ml_predictor.py
python scripts/run_walk_forward_ai.py

# 4. Dashboard
streamlit run src/dashboard/dashboard_v2.py

# 5. Docker
docker-compose up -d

# 6. Kubernetes (AWS)
cd terraform && terraform init && terraform apply
cd ../k8s && kubectl apply -f namespace.yaml -f configmap.yaml -f secret.yaml -f pvc.yaml
kubectl apply -f deployment-bot.yaml -f deployment-paper.yaml -f deployment-ml.yaml -f deployment-dashboard.yaml
kubectl apply -f service-dashboard.yaml
```

## 📊 Assets Supportati

| Asset | Classe | Volatilità | Ore | Margini |
|-------|--------|-----------|-----|---------|
| XAUUSD | Commodity | High | 24/5 | ~$11,000 |
| EURUSD | Forex | Medium | 24/5 | ~$500 |
| GBPUSD | Forex | High | 24/5 | ~$500 |
| USDJPY | Forex | Medium | 24/5 | ~$500 |
| BTCUSD | Crypto | Extreme | 24/7 | ~$2,000 |

## 🛡️ Safety Rules

- `LIVE_MODE=false` di default
- AI reasoning **solo consulenziale**
- ML **solo predizione**
- Telegram **solo notifiche**
- **Safety Gate obbligatorio** per broker reali:
  1. `LIVE_MODE=true` in .env
  2. File `.LIVE_TRADING_APPROVED` con firma esplicita
  3. Limiti giornalieri configurati
  4. Simboli approvati esplicitamente
- Broker demo read-only con guardrails
- Ogni trade ha stop loss
- Ogni trade passa dal risk manager + portfolio risk
- Nessuna API key in codice
