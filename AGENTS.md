# AGENTS.md - XAU Auto Trader V2 Enterprise

## Project goal

Enterprise-grade Python modular trading research system for multi-asset trading with AI/ML, cloud-native deployment, and institutional-grade risk management.

## Architecture Layers

1. **Data Layer**: CSV, MT5 Bridge, WebSocket, Yahoo Finance
2. **Technical Layer**: EMA, RSI, ATR, MACD, ADX, Market Structure
3. **Smart Money**: FVG, Order Blocks, Liquidity Sweeps
4. **Macro Layer**: DXY, US10Y, VIX, SPX500, Correlation
5. **News Layer**: ForexFactory Scraper, Investing.com Scraper
6. **AI Reasoning**: Context Builder, Score Composer, Explanations, Warnings
7. **ML Layer**: Trade Features, Predictor, Regime Detection, Continuous Training
8. **Multi-Asset**: XAU, EUR, GBP, BTC, JPY with asset-specific configs
9. **Strategy Lab**: Regime-based Strategy Selection, Walk-Forward Analysis
10. **Advanced Orders**: Trailing Stop, OCO, Bracket, Scale-In/Out, Expiry
11. **Portfolio Risk**: Portfolio Heat, Cross-Asset Correlation, Diversification
12. **Derivatives**: Black-Scholes Options (Greeks), Futures Calendar, Contango
13. **Broker Integration**: OANDA, IG, Interactive Brokers with Safety Gate
14. **Risk Engine**: Position Sizing, Drawdown, Consecutive Losses
15. **Execution**: Paper Trading V2, Live Paper Engine, Demo Broker, Real Broker
16. **Notifications**: Telegram Bot (5 types)
17. **Monitoring**: Streamlit Dashboard, Prometheus, CloudWatch
18. **Deployment**: Docker, Docker Compose, Kubernetes (EKS), Terraform (AWS)

## Safety Rules

### Absolute Rules (never bypass)
- LIVE_MODE must remain false by default
- No real broker API calls without explicit user approval
- No real orders without SafetyGate approval file
- No API keys in code
- No .env committed to Git
- Every tradable signal must have stop loss
- Every trade must pass the risk manager AND portfolio risk manager
- AI reasoning cannot execute trades
- ML predictions cannot execute trades
- Telegram bot cannot execute trades

### Real Trading Safety Gate (mandatory)
To enable real trading, ALL of the following must be true:
1. LIVE_MODE=true in environment
2. `.LIVE_TRADING_APPROVED` file exists with explicit approval
3. Daily risk limit configured and not exceeded
4. Daily trade limit configured and not exceeded
5. Symbol explicitly in allowed_symbols list
6. All orders logged to `reports/safety/real_trading_attempts.log`

## Environment

```bash
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

## Docker Deployment

```bash
docker-compose up -d
```

Services:
- bot: backtest engine
- paper_trader: continuous paper trading
- ml_trainer: continuous ML training
- dashboard: Streamlit on port 8501
- telegram_bot: notifications
- scheduler: cron jobs

## Kubernetes Deployment

```bash
cd terraform && terraform init && terraform apply
cd ../k8s && kubectl apply -f .
```

## Coding Rules

- Keep modules small and testable.
- Add or update tests for every code change.
- Do not break existing tests.
- Prefer simple, readable Python.
- Do not add heavy dependencies unless necessary.
- Do not commit generated CSV files, reports, databases, .venv, or .env.
- Respect config.yaml as the source of adjustable strategy/risk parameters.
- All new features must be configurable via config.yaml.
- Multi-asset support must not break XAU/USD default behavior.
- Safety gate must be enforced for ALL real broker implementations.
