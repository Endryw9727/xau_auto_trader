from datetime import datetime

from src.monitoring import TelegramReport


def test_telegram_report_model_is_report_only():
    report = TelegramReport(
        title="Paper Forward Status",
        status="OK",
        message="No open trades. Paper mode only.",
        severity="INFO",
    )

    assert report.title == "Paper Forward Status"
    assert report.status == "OK"
    assert report.severity == "INFO"
    assert isinstance(report.created_at, datetime)
    assert "Paper" in report.message
