---
title: Visione — Trading Statistico e Apprendimento
tags: [jarvis, visione, trading, statistica, montecarlo, aspettativa, demo]
created: 2026-07-01
status: living-document
---

# Visione — Trading Statistico e Apprendimento

> [!abstract] In una frase
> Il bot non deve vincere ogni trade. Deve avere **aspettativa positiva**,
> capire la **varianza**, e **imparare dagli errori** finché non raggiunge un
> equilibrio profittevole — tutto su **conto demo**, senza fretta.

## 1. Il principio: non serve il 100% di win rate

Nessuno ha il 100% di operazioni vincenti. Qui entra la statistica: con un
**rischio/rendimento (R:R)** adeguato si può essere molto profittevoli pur
perdendo la maggioranza dei trade.

**Win rate di pareggio** = `1 / (1 + R)`

| R:R | Win rate minimo per NON perdere | Commento |
|----:|:-------------------------------:|----------|
| 1:1 | 50.0% | serve più della metà vincenti |
| 1.5:1 | 40.0% | |
| 2:1 | **33.3%** | basta 1 vinto ogni 3 |
| 3:1 | 25.0% | 1 vinto ogni 4 |
| 4:1 | 20.0% | 1 vinto ogni 5 |

**Aspettativa per trade** (in unità R, una perdita piena = −1R):
`E = win_rate × R − (1 − win_rate)`

Se `E > 0`, nel lungo periodo si è in profitto. Esempio: R:R = 2, win rate 45%
→ `E = 0.45×2 − 0.55 = +0.35R` per trade. Su 100 trade ≈ +35R lordi.

→ Implementato in `src/analysis/trade_simulation.py`
(`breakeven_win_rate`, `expectancy_r`, `required_win_rate`, `kelly_fraction`).

## 2. Monte Carlo: capire la varianza

Sapere che l'aspettativa è positiva **non basta**: anche un sistema vincente ha
strisce perdenti che possono mandare in rovina se il rischio è troppo alto.

**Metodo**: si simulano migliaia di *sequenze* di trade (1000+ scenari) e si
guarda la **distribuzione** dei risultati:
- probabilità di chiudere in profitto;
- drawdown massimo (mediano e peggiore);
- probabilità di rovina (perdita di capitale oltre una soglia);
- percentili di rendimento finale (5° / mediana / 95°).

Due varianti:
1. **Parametrica** — fisso win rate + R:R e simulo con rischio frazionario fisso.
2. **Bootstrap** — ricampiono i *rendimenti storici reali* dei trade, così
   mantengo le code grasse e l'asimmetria vere della strategia.

→ Implementato in `src/analysis/trade_simulation.py`
(`monte_carlo_fixed`, `bootstrap_monte_carlo`).

## 3. Filtri e conferme (idee, non promesse)

Gli **indicatori più utili** vanno usati come **filtro aggiuntivo / aiuto**, non
come oracoli: servono a migliorare l'attendibilità di un ingresso, non a
garantirlo. Fonti di segnale da studiare come *famiglie di ipotesi*:
- struttura del grafico e price action (già: sessioni Asia/Londra/NY, sweep);
- regimi di volatilità (alta/bassa) e trend vs mean-reversion condizionati;
- studio dei **volumi** / proxy di order-flow da OHLCV;
- **news** ed eventi macro come filtro (blocco/contesto);
- lead-lag cross-asset e stagionalità.

Regola d'oro: **ogni ipotesi passa dal validatore** (walk-forward + Bonferroni/BH
+ [[#5 Anti-illusione DSR e PBO|DSR/PBO]]). Un filtro non si allenta mai per
fare più trade.

## 4. Il ciclo di apprendimento

```
ipotesi → test statistico → (se profittevole) demo → osserva esito
   ↑                                                        │
   └──────── correggi ← capisci l'errore ← se sbaglia ──────┘
```

Quando un'analisi sbaglia, **non si nasconde**: si registra *perché* era
sbagliata e si aggiorna la conoscenza. Questo è il ruolo del **secondo cervello
(jarvis)**: raccoglie e immagazzina tutto ciò che impariamo, ed è collegato a
git così che le lezioni siano versionate e permanenti. Obiettivo doppio:
1. costruire un sistema che **si auto-corregge e si evolve** ogni giorno;
2. far **imparare il trading vero** all'operatore umano, come i professionisti.

## 5. Anti-illusione: DSR e PBO

La regola numero uno: **il sistema non deve illudersi.** Più ipotesi si testano,
più è facile trovare "edge" falsi per puro caso. Per questo, oltre a
Bonferroni/BH, ogni scoperta deve battere:
- **Deflated Sharpe Ratio (DSR)** — corregge lo Sharpe per quante strategie sono
  state provate; la barra della "fortuna" sale con il numero di tentativi.
- **Probability of Backtest Overfitting (PBO)** — quanto spesso la migliore
  in-sample crolla out-of-sample.

Un edge è credibile solo con **DSR alto (>~0.95) E PBO basso (<~0.5)**.

→ Implementato in `src/analysis/overfitting.py` e `src/analysis/edge_overfitting.py`.

## 6. Regole di sicurezza (invariabili)

- Solo **demo**, mai live reale senza approvazione manuale esplicita.
- Nessun filtro di rischio si indebolisce per aumentare il numero di trade.
- Prima si **logga** la motivazione di un rifiuto, poi si valuta un filtro.
- La ricerca è **read-only**: non invia ordini.

> [!note] Stato
> Documento vivo. Aggiornato mano a mano che il sistema impara. Ultima
> revisione: motore anti-overfitting + simulazione aspettativa/Monte Carlo
> costruiti e testati.
