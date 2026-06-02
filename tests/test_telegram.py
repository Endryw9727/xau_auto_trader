"""Tests for Telegram notifier."""
import os

from src.telegram.telegram_notifier import TelegramConfig, TelegramNotifier, load_telegram_config


def test_load_config_disabled():
    # Ensure no env vars are set
    for key in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]:
        os.environ.pop(key, None)
    config = load_telegram_config()
    assert config.enabled is False


def test_telegram_config():
    config = TelegramConfig(
        enabled=True,
        bot_token="test_token",
        chat_id="123456",
        notify_signals=True,
    )
    assert config.bot_token == "test_token"
    assert config.notify_signals is True


def test_notifier_disabled():
    config = TelegramConfig(enabled=False, bot_token="", chat_id="")
    notifier = TelegramNotifier(config)
    result = notifier.send_message("test")
    assert result["sent"] is False


def test_notify_signal_disabled():
    config = TelegramConfig(enabled=False, bot_token="", chat_id="")
    notifier = TelegramNotifier(config)
    result = notifier.notify_signal("BUY", 2350, 2340, 2370, 2.5)
    assert result["sent"] is False
