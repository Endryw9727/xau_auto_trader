import ast
from pathlib import Path

import pandas as pd

from src.v2_shadow import run_v2_shadow_report
from src.v2_shadow.ai_reasoning import compose_shadow_reasoning
from src.v2_shadow.indicators import add_core_shadow_indicators
from src.v2_shadow.macro import build_shadow_macro_snapshot
from src.v2_shadow.news import build_shadow_news_warning
from src.v2_shadow.report import load_latest_candidate_context
from src.v2_shadow.smart_money import analyze_shadow_smc, detect_liquidity_sweeps, detect_order_blocks


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_ohlc() -> pd.DataFrame:
    index = pd.date_range("2026-05-25 09:00:00", periods=12, freq="15min")
    return pd.DataFrame(
        {
            "Open": [100, 101, 102, 103, 104, 106, 105, 107, 106, 104, 103, 105],
            "High": [101, 102, 103, 104, 105, 108, 106, 109, 107, 105, 106, 108],
            "Low": [99, 100, 101, 102, 103, 104, 102, 105, 101, 99, 101, 104],
            "Close": [100.5, 101.5, 102.5, 103.5, 104.5, 105.0, 105.5, 106.0, 102.0, 104.0, 105.5, 107.0],
            "Volume": [1000] * 12,
        },
        index=index,
    )


def test_v2_shadow_modules_importable():
    frame = make_ohlc()
    enriched = add_core_shadow_indicators(frame)
    smc = analyze_shadow_smc(frame)
    macro = build_shadow_macro_snapshot(frame)
    news = build_shadow_news_warning()
    reasoning = compose_shadow_reasoning(
        candidate=None,
        indicator_snapshot={},
        smc=smc,
        macro=macro,
        news=news,
    )

    assert "v2_shadow_ema_20" in enriched.columns
    assert smc.bias in {"BULLISH", "BEARISH", "NEUTRAL"}
    assert macro.advisory_only is True
    assert news.advisory_only is True
    assert reasoning.report_only is True
    assert reasoning.can_execute is False


def test_v2_shadow_report_dry_run_no_candidate(tmp_path):
    csv_path = tmp_path / "xauusd.csv"
    output_dir = tmp_path / "shadow"
    frame = make_ohlc().reset_index().rename(columns={"index": "Date"})
    frame.to_csv(csv_path, index=False)

    report = run_v2_shadow_report(
        market_data_path=csv_path,
        candidate_log_path=tmp_path / "missing_log.csv",
        output_dir=output_dir,
        dry_run=True,
    )

    json_path = output_dir / "v2_shadow_latest.json"
    txt_path = output_dir / "v2_shadow_latest.txt"
    assert report.status == "NO_CANDIDATE"
    assert report.safety["orders_sent"] is False
    assert report.safety["broker_called"] is False
    assert report.safety["execution_called"] is False
    assert json_path.exists()
    assert txt_path.exists()
    assert "NO_CANDIDATE" in txt_path.read_text(encoding="utf-8")


def test_v2_shadow_reads_candidate_log_without_execution(tmp_path):
    log_path = tmp_path / "v51_demo_execution_log.csv"
    pd.DataFrame(
        [
            {
                "signal_id": "V51-TEST",
                "side": "BUY",
                "status": "NO_TRADE",
                "reason": "test candidate",
                "score": 80.0,
                "risk_reward": 1.4,
            }
        ]
    ).to_csv(log_path, index=False)

    candidate = load_latest_candidate_context(log_path)

    assert candidate is not None
    assert candidate["signal_id"] == "V51-TEST"
    assert candidate["side"] == "BUY"


def test_v2_shadow_does_not_import_broker_execution_or_paper_engine():
    forbidden_prefixes = (
        "src.broker",
        "src.execution",
        "src.paper",
        "MetaTrader5",
        "oanda",
        "ig_client",
        "ib_client",
    )
    paths = list((PROJECT_ROOT / "src" / "v2_shadow").glob("*.py")) + [PROJECT_ROOT / "scripts" / "run_v2_shadow_report.py"]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(forbidden_prefixes), f"{path} imports {alias.name}"
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(forbidden_prefixes), f"{path} imports {node.module}"


def test_v2_shadow_smc_future_confirmed_features_have_available_at():
    frame = make_ohlc()
    order_blocks = detect_order_blocks(frame)
    sweeps = detect_liquidity_sweeps(frame)
    features = list(order_blocks) + list(sweeps)

    assert features
    for feature in features:
        assert feature.available_at >= feature.event_time

    first_feature = min(features, key=lambda feature: feature.available_at)
    before_available = analyze_shadow_smc(frame, as_of=first_feature.available_at - pd.Timedelta(minutes=1))
    assert all(feature.available_at <= first_feature.available_at - pd.Timedelta(minutes=1) for feature in before_available.features)
