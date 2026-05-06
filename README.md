# XAU Auto Trader

Software Python modulare per studio, backtest e paper trading su XAU/USD.

## Obiettivo

Creare un sistema professionale per:
- caricare dati storici
- generare segnali
- gestire rischio
- fare backtest
- simulare paper trading
- salvare trade su SQLite
- produrre report

## Sicurezza

Il live trading è disabilitato di default.

Regole:
- `LIVE_MODE=false`
- nessuna API key nel codice
- nessun ordine reale nella prima fase
- stop loss obbligatorio
- risk manager obbligatorio
- test prima di ogni modifica importante

## Setup

```bash
source .venv/bin/activate
pip install -r requirements.txt
pytest

```bash
cat > tests/test_placeholder.py << 'EOF'
def test_project_bootstrap():
    assert True
