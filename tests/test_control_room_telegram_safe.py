from src.control_room.orchestrator import load_control_room_config
from src.control_room.telegram_reporter import ControlRoomTelegramReport, maybe_emit_telegram_report


def test_telegram_disabled_sends_nothing(monkeypatch):
    config = load_control_room_config()
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    report = ControlRoomTelegramReport("title", "OK", "message", "INFO")

    result = maybe_emit_telegram_report(config, report)

    assert result["status"] == "OK"
    assert result["telegram_sent"] is False


def test_telegram_enabled_without_token_is_warning(tmp_path, monkeypatch):
    raw = open("config/control_room.yaml", encoding="utf-8").read().replace("telegram_enabled: false", "telegram_enabled: true")
    path = tmp_path / "control_room.yaml"
    path.write_text(raw, encoding="utf-8")
    config = load_control_room_config(path)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    result = maybe_emit_telegram_report(config, ControlRoomTelegramReport("title", "OK", "message", "INFO"))

    assert result["status"] == "WARNING"
    assert result["telegram_sent"] is False
