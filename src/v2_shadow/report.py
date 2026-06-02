"""V2 shadow report orchestration for V1.

The report is read-only: it reads V1 market data and logs, builds diagnostic
overlays, and writes shadow artifacts. It never calls broker or execution code.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.v2_shadow.ai_reasoning import ShadowAIReasoning, compose_shadow_reasoning
from src.v2_shadow.indicators import add_core_shadow_indicators, latest_indicator_snapshot
from src.v2_shadow.macro import ShadowMacroSnapshot, build_shadow_macro_snapshot
from src.v2_shadow.news import ShadowNewsWarning, build_shadow_news_warning
from src.v2_shadow.smart_money import ShadowSMCReport, analyze_shadow_smc


DEFAULT_SHADOW_OUTPUT_DIR = Path("reports/shadow")
DEFAULT_MARKET_DATA_PATH = Path("data/raw/xauusd.csv")
DEFAULT_CANDIDATE_LOG_PATH = Path("reports/demo_execution/v51_demo_execution_log.csv")


@dataclass(frozen=True)
class V2ShadowReport:
    """Complete read-only V2 shadow report."""

    status: str
    generated_at: str
    source: str
    market_data: dict[str, Any]
    candidate: dict[str, Any] | None
    indicators: dict[str, float | None]
    smart_money: ShadowSMCReport
    macro: ShadowMacroSnapshot
    news: ShadowNewsWarning
    ai_reasoning: ShadowAIReasoning
    safety: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "generated_at": self.generated_at,
            "source": self.source,
            "market_data": self.market_data,
            "candidate": self.candidate,
            "indicators": self.indicators,
            "smart_money": self.smart_money.to_dict(),
            "macro": self.macro.to_dict(),
            "news": self.news.to_dict(),
            "ai_reasoning": self.ai_reasoning.to_dict(),
            "safety": self.safety,
        }


def run_v2_shadow_report(
    *,
    market_data_path: str | Path = DEFAULT_MARKET_DATA_PATH,
    candidate_log_path: str | Path = DEFAULT_CANDIDATE_LOG_PATH,
    output_dir: str | Path = DEFAULT_SHADOW_OUTPUT_DIR,
    dry_run: bool = True,
    now: pd.Timestamp | None = None,
    limit_candles: int = 500,
) -> V2ShadowReport:
    """Build and write a V2 shadow report."""
    now_ts = pd.Timestamp.now(tz="UTC") if now is None else _utc_timestamp(now)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    market_data = load_market_data(market_data_path, limit_candles=limit_candles)
    if market_data.empty:
        indicator_snapshot: dict[str, float | None] = {}
        smc_report = ShadowSMCReport("NEUTRAL", (), None, None, "No market data available.")
        macro_snapshot = build_shadow_macro_snapshot(None)
        candidate = load_latest_candidate_context(candidate_log_path)
        status = "DATA_MISSING" if candidate is not None else "NO_CANDIDATE"
        market_summary = {"path": str(market_data_path), "rows": 0, "latest_time": None}
    else:
        enriched = add_core_shadow_indicators(market_data)
        indicator_snapshot = latest_indicator_snapshot(enriched)
        smc_report = analyze_shadow_smc(market_data, as_of=market_data.index[-1])
        macro_snapshot = build_shadow_macro_snapshot(market_data)
        candidate = load_latest_candidate_context(candidate_log_path)
        status = "OK" if candidate is not None else "NO_CANDIDATE"
        market_summary = {
            "path": str(market_data_path),
            "rows": int(len(market_data)),
            "latest_time": pd.Timestamp(market_data.index[-1]).isoformat(),
            "latest_close": _float_or_none(market_data["Close"].iloc[-1]),
        }

    news_warning = build_shadow_news_warning()
    ai_reasoning = compose_shadow_reasoning(
        candidate=candidate,
        indicator_snapshot=indicator_snapshot,
        smc=smc_report,
        macro=macro_snapshot,
        news=news_warning,
    )
    report = V2ShadowReport(
        status=status,
        generated_at=now_ts.isoformat(),
        source="v2_shadow_read_only",
        market_data=market_summary,
        candidate=candidate,
        indicators=indicator_snapshot,
        smart_money=smc_report,
        macro=macro_snapshot,
        news=news_warning,
        ai_reasoning=ai_reasoning,
        safety={
            "dry_run": dry_run,
            "report_only": True,
            "orders_sent": False,
            "broker_called": False,
            "execution_called": False,
            "live_trade_filter": False,
        },
    )
    write_v2_shadow_report(report, output_path)
    return report


def load_market_data(path: str | Path, *, limit_candles: int = 500) -> pd.DataFrame:
    """Load V1 OHLCV CSV if available."""
    csv_path = Path(path)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return pd.DataFrame()
    frame = pd.read_csv(csv_path)
    if "Date" in frame.columns:
        index = pd.to_datetime(frame["Date"], errors="coerce")
        frame = frame.drop(columns=["Date"])
    else:
        index = pd.to_datetime(frame.index, errors="coerce")
    frame.index = index
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"]).sort_index()
    columns = [column for column in ("Open", "High", "Low", "Close", "Volume") if column in frame.columns]
    result = frame[columns].tail(limit_candles).copy()
    for column in columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result.dropna(subset=["Open", "High", "Low", "Close"])


def load_latest_candidate_context(path: str | Path) -> dict[str, Any] | None:
    """Load latest V51 candidate/log context if present."""
    log_path = Path(path)
    if not log_path.exists() or log_path.stat().st_size == 0:
        return None
    try:
        frame = pd.read_csv(log_path)
    except Exception:
        return None
    if frame.empty:
        return None
    signal_frame = frame[frame.get("signal_id", pd.Series(dtype=object)).notna()].copy()
    if signal_frame.empty:
        return None
    row = signal_frame.iloc[-1]
    signal_id = _text_or_none(row.get("signal_id"))
    side = _text_or_none(row.get("side"))
    if not signal_id or not side:
        return None
    return {
        "signal_id": signal_id,
        "side": side,
        "status": _text_or_none(row.get("status")),
        "reason": _text_or_none(row.get("reason")),
        "candle_time": _text_or_none(row.get("candle_time")),
        "selected_candidate_time": _text_or_none(row.get("selected_candidate_time")),
        "score": _float_or_none(row.get("score")),
        "risk_reward": _float_or_none(row.get("risk_reward")),
        "source_log": str(log_path),
    }


def write_v2_shadow_report(report: V2ShadowReport, output_dir: str | Path) -> tuple[Path, Path]:
    """Write latest JSON and text shadow artifacts."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "v2_shadow_latest.json"
    txt_path = output_path / "v2_shadow_latest.txt"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    txt_path.write_text(format_v2_shadow_text(report), encoding="utf-8")
    return json_path, txt_path


def format_v2_shadow_text(report: V2ShadowReport) -> str:
    """Format a concise human-readable shadow report."""
    candidate = report.candidate or {}
    lines = [
        "V2 Shadow Report",
        f"Generated at: {report.generated_at}",
        f"Status: {report.status}",
        "",
        "Safety",
        "- report_only: True",
        "- orders_sent: False",
        "- broker_called: False",
        "- execution_called: False",
        "",
        "Market",
        f"- rows: {report.market_data.get('rows')}",
        f"- latest_time: {report.market_data.get('latest_time')}",
        f"- latest_close: {report.market_data.get('latest_close')}",
        "",
        "Candidate",
        f"- signal_id: {candidate.get('signal_id') or 'NO_CANDIDATE'}",
        f"- side: {candidate.get('side') or 'n/a'}",
        f"- reason: {candidate.get('reason') or 'n/a'}",
        "",
        "Shadow Layers",
        f"- SMC: {report.smart_money.explanation}",
        f"- Macro: {report.macro.explanation}",
        f"- News: {report.news.warning}",
        f"- AI: {report.ai_reasoning.explanation}",
    ]
    return "\n".join(lines) + "\n"


def _utc_timestamp(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _float_or_none(value: object) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    return text or None
