from src.macro import MacroSnapshot


def test_macro_snapshot_model_defaults_are_neutral():
    snapshot = MacroSnapshot()

    assert snapshot.dxy_bias == "neutral"
    assert snapshot.yields_bias == "neutral"
    assert snapshot.risk_sentiment == "neutral"
    assert snapshot.macro_score_long == 0.0
    assert snapshot.macro_score_short == 0.0
    assert snapshot.notes == ()


def test_macro_snapshot_model_accepts_advisory_scores():
    snapshot = MacroSnapshot(
        dxy_bias="bearish_usd",
        yields_bias="gold_supportive",
        news_risk="high",
        risk_sentiment="risk_off",
        macro_score_long=0.6,
        macro_score_short=0.2,
        notes=("CPI day: advisory caution",),
    )

    assert snapshot.news_risk == "high"
    assert snapshot.macro_score_long > snapshot.macro_score_short
    assert "CPI" in snapshot.notes[0]
