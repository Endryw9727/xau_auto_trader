"""Realistic MOCK data provider for the Research Console.

This module DOES NOT implement quantitative/statistical research logic. The real
statistics live in an external Python API (configured via API_BASE_URL). Here we
only synthesise plausible, schema-correct payloads so the UI is fully functional
even when the external API is not connected.
"""
import hashlib
import math
import random
from datetime import datetime, timezone, timedelta

SESSIONS = ["ASIA", "LONDON", "NEW YORK"]
DIRECTIONS = ["LONG", "SHORT"]
CONDITIONS = ["PRE_UP", "PRE_DOWN", "HIGH_VOL", "LOW_VOL", "TREND_UP", "RANGE"]
HYPOTHESES = ["CONTINUATION", "REVERSAL", "MEAN_REVERSION", "BREAKOUT"]

DEFAULT_INSTRUMENTS = [
    {"symbol": "XAUUSD", "rows": 17226, "cost_per_trade": 0.20},
    {"symbol": "EURUSD", "rows": 21540, "cost_per_trade": 0.08},
    {"symbol": "GBPUSD", "rows": 19980, "cost_per_trade": 0.10},
    {"symbol": "USDJPY", "rows": 20310, "cost_per_trade": 0.09},
    {"symbol": "BTCUSD", "rows": 35040, "cost_per_trade": 0.50},
    {"symbol": "SPX500", "rows": 15120, "cost_per_trade": 0.15},
]


def _rng(*parts) -> random.Random:
    # SHA-256 used only for DETERMINISTIC mock-data seeding (not security).
    seed = int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest(), 16) % (2**32)
    return random.Random(seed)


def _p_from_t(t: float) -> float:
    z = abs(t)
    cdf = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return round(2 * (1 - cdf), 4)


def _date_range(rows: int):
    last = datetime.now(timezone.utc).replace(microsecond=0)
    first = last - timedelta(hours=rows)
    return first.isoformat(), last.isoformat()


def health() -> dict:
    return {"status": "ok", "live_armed": False}


def instruments() -> dict:
    out = []
    for inst in DEFAULT_INSTRUMENTS:
        first, last = _date_range(inst["rows"])
        out.append({
            "symbol": inst["symbol"],
            "has_data": True,
            "rows": inst["rows"],
            "first": first,
            "last": last,
            "cost_per_trade": inst["cost_per_trade"],
            "source": "bundled",
        })
    return {"instruments": out}


def _leg(symbol: str, *tag) -> dict:
    r = _rng(symbol, *tag)
    t = round(r.gauss(0.35, 0.95), 2)
    p = _p_from_t(t)
    family = 68
    bonf = p < (0.05 / family)
    bh = p < 0.02
    robust = bool(bh and abs(t) > 2.5)
    return {
        "n_trades": r.randint(180, 2400),
        "is_t_stat": round(t + r.gauss(0.4, 0.3), 2),
        "oos_t_stat": t,
        "sharpe": round(r.uniform(-0.4, 1.8), 2),
        "win_rate": round(r.uniform(0.41, 0.62), 3),
        "expectancy": round(r.uniform(-0.05, 0.22), 4),
        "p_value": p,
        "bonferroni_significant": bonf,
        "bh_significant": bh,
        "mtc_robust": robust,
    }


def _verdict(symbol: str):
    best = None
    detail = []
    for s in SESSIONS:
        for d in DIRECTIONS:
            leg = _leg(symbol, "session", s, d)
            row = {"symbol": symbol, "session": s, "direction": d, **leg}
            detail.append(row)
            if best is None or leg["oos_t_stat"] > best["oos_t_stat"]:
                best = {"session": s, "direction": d, "oos_t_stat": leg["oos_t_stat"]}
    keep = best["oos_t_stat"] >= 1.5
    return {
        "symbol": symbol,
        "verdict": "KEEP" if keep else "EXCLUDE",
        "best_session": best["session"],
        "best_direction": best["direction"],
        "best_oos_t_stat": best["oos_t_stat"],
    }, detail


def session_scan(symbols) -> dict:
    verdicts, detail = [], []
    for sym in symbols:
        v, d = _verdict(sym)
        verdicts.append(v)
        detail.extend(d)
    return {"status": "OK", "verdicts": verdicts, "detail": detail}


def ny_conditional(symbols) -> dict:
    verdicts, detail = [], []
    for sym in symbols:
        best = None
        for cond in CONDITIONS:
            for hyp in HYPOTHESES:
                for d in DIRECTIONS:
                    leg = _leg(sym, "ny", cond, hyp, d)
                    row = {"symbol": sym, "condition": cond, "hypothesis": hyp, "direction": d, **leg}
                    detail.append(row)
                    if best is None or leg["oos_t_stat"] > best["oos_t_stat"]:
                        best = {"condition": cond, "hypothesis": hyp, "direction": d, "oos_t_stat": leg["oos_t_stat"]}
        keep = best["oos_t_stat"] >= 1.5
        verdicts.append({
            "symbol": sym,
            "verdict": "KEEP" if keep else "EXCLUDE",
            "best_session": "NEW YORK",
            "best_condition": best["condition"],
            "best_hypothesis": best["hypothesis"],
            "best_direction": best["direction"],
            "best_oos_t_stat": best["oos_t_stat"],
        })
    return {"status": "OK", "verdicts": verdicts, "detail": detail}


def overnight(symbols) -> dict:
    verdicts, detail = [], []
    for sym in symbols:
        best = None
        for d in DIRECTIONS:
            leg = _leg(sym, "overnight", d)
            row = {"symbol": sym, "leg": "OVERNIGHT", "direction": d, **leg}
            detail.append(row)
            if best is None or leg["oos_t_stat"] > best["oos_t_stat"]:
                best = {"direction": d, "oos_t_stat": leg["oos_t_stat"], "p_value": leg["p_value"],
                        "bh_significant": leg["bh_significant"], "mtc_robust": leg["mtc_robust"]}
        keep = best["mtc_robust"] or best["oos_t_stat"] >= 1.8
        verdicts.append({
            "symbol": sym,
            "verdict": "KEEP" if keep else "EXCLUDE",
            "best_session": "OVERNIGHT",
            "best_direction": best["direction"],
            "best_oos_t_stat": best["oos_t_stat"],
            "p_value": best["p_value"],
            "bh_significant": best["bh_significant"],
            "mtc_robust": best["mtc_robust"],
        })
    return {"status": "OK", "verdicts": verdicts, "detail": detail}


def significance_audit(symbols) -> dict:
    rows = []
    for sym in symbols:
        for cond in CONDITIONS:
            for hyp in HYPOTHESES:
                for d in DIRECTIONS:
                    leg = _leg(sym, "ny", cond, hyp, d)
                    rows.append({
                        "symbol": sym,
                        "combo": f"{cond}/{d}/{hyp}",
                        "oos_t_stat": leg["oos_t_stat"],
                        "p_value": leg["p_value"],
                        "bonferroni_significant": leg["bonferroni_significant"],
                        "bh_significant": leg["bh_significant"],
                        "mtc_robust": leg["mtc_robust"],
                    })
    rows.sort(key=lambda r: r["oos_t_stat"], reverse=True)
    family_size = len(rows)
    survivors = sum(1 for r in rows if r["mtc_robust"])
    return {"family_size": family_size, "mtc_survivors": survivors, "rows": rows}


def rejection_taxonomy() -> dict:
    r = _rng("rejection")
    cats = ["SPREAD_TOO_WIDE", "OUTSIDE_SESSION", "LOW_LIQUIDITY", "SIGNAL_CONFLICT",
            "MAX_POSITIONS", "COOLDOWN_ACTIVE", "VOL_FILTER", "NEWS_BLACKOUT"]
    total = r.randint(8000, 14000)
    buckets = []
    rem = total
    for i, c in enumerate(cats):
        n = r.randint(200, 2200) if i < len(cats) - 1 else max(rem, 0)
        n = min(n, rem)
        rem -= n
        buckets.append({"reason": c, "count": n, "pct": round(100 * n / total, 1)})
    buckets.sort(key=lambda x: x["count"], reverse=True)
    return {"report": "rejection_taxonomy", "total_rejections": total, "buckets": buckets}


def market_structure() -> dict:
    r = _rng("structure")
    regimes = ["TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOL", "LOW_VOL"]
    return {
        "report": "market_structure",
        "regimes": [{"regime": x, "pct_time": round(r.uniform(8, 35), 1),
                     "avg_atr": round(r.uniform(0.4, 2.4), 2),
                     "trades": r.randint(120, 1800)} for x in regimes],
        "trend_strength_adx": round(r.uniform(14, 38), 1),
        "regime_stability": round(r.uniform(0.55, 0.9), 2),
    }


def quality_review() -> dict:
    r = _rng("quality")
    checks = [
        ("Data continuity", r.choice(["PASS", "PASS", "WARN"])),
        ("Lookahead bias guard", "PASS"),
        ("Slippage model applied", "PASS"),
        ("Cost per trade applied", "PASS"),
        ("Out-of-sample split", r.choice(["PASS", "PASS", "WARN"])),
        ("Survivorship bias", r.choice(["PASS", "WARN"])),
        ("Parameter overfit scan", r.choice(["PASS", "WARN", "FAIL"])),
    ]
    score = round(sum(1 for _, s in checks if s == "PASS") / len(checks) * 100)
    return {
        "report": "quality_review",
        "score": score,
        "checks": [{"name": n, "status": s} for n, s in checks],
    }


def demo_readiness() -> dict:
    r = _rng("demo")
    gates = [
        ("Significance audit reviewed", True),
        ("mtc_robust survivors present", r.random() > 0.5),
        ("Risk limits configured", True),
        ("Live execution DISARMED", True),
        ("allow_real_live == false", True),
        ("Manual sign-off", False),
    ]
    ready = all(v for _, v in gates)
    return {
        "report": "demo_readiness",
        "ready_for_demo": ready,
        "live_armed": False,
        "allow_real_live": False,
        "gates": [{"gate": n, "passed": v} for n, v in gates],
    }


def synthetic_series(symbol: str, rows: int):
    r = _rng("synthetic", symbol, rows)
    price = r.uniform(50, 2000)
    series = []
    now = datetime.now(timezone.utc)
    for i in range(rows):
        drift = r.gauss(0, 0.004)
        o = price
        c = max(0.01, price * (1 + drift))
        h = max(o, c) * (1 + abs(r.gauss(0, 0.002)))
        low = min(o, c) * (1 - abs(r.gauss(0, 0.002)))
        v = r.randint(500, 50000)
        ts = (now - timedelta(hours=rows - i)).isoformat()
        series.append({"date": ts, "open": round(o, 2), "high": round(h, 2),
                       "low": round(low, 2), "close": round(c, 2), "volume": v})
        price = c
    return series
