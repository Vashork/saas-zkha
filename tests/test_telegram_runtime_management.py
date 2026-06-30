"""Tests for DB-backed Telegram runtime management helpers and wiring."""

from pathlib import Path
from types import SimpleNamespace

from app.bot.management import (
    MANAGED_TELEGRAM_COMMANDS,
    is_telegram_command_enabled,
    telegram_command_default_settings,
    telegram_command_setting_key,
)
from app.bot.security import _telegram_command_name

ROOT = Path(__file__).resolve().parents[1]


def test_telegram_command_default_settings_are_enabled():
    defaults = telegram_command_default_settings()

    assert set(defaults) == {telegram_command_setting_key(command) for command in MANAGED_TELEGRAM_COMMANDS}
    assert set(defaults.values()) == {"1"}
    for command in MANAGED_TELEGRAM_COMMANDS:
        assert is_telegram_command_enabled(defaults, command) is True


def test_telegram_command_enabled_respects_disabled_managed_command():
    settings = telegram_command_default_settings()
    settings[telegram_command_setting_key("balance")] = "0"

    assert is_telegram_command_enabled(settings, "balance") is False
    assert is_telegram_command_enabled(settings, "/balance") is False
    assert is_telegram_command_enabled(settings, "unknown") is True
    assert is_telegram_command_enabled(settings, None) is True


def test_telegram_command_name_extracts_plain_and_bot_mention_commands():
    assert _telegram_command_name(SimpleNamespace(text="/help")) == "help"
    assert _telegram_command_name(SimpleNamespace(text="/balance@HomeBot now")) == "balance"
    assert _telegram_command_name(SimpleNamespace(text="#оплачено #mos")) is None
    assert _telegram_command_name(SimpleNamespace(text=None)) is None


def test_telegram_command_toggle_source_wiring():
    telegram_html = (ROOT / "app" / "web" / "templates" / "telegram.html").read_text(encoding="utf-8")
    telegram_route = (ROOT / "app" / "web" / "routes" / "telegram.py").read_text(encoding="utf-8")
    security_py = (ROOT / "app" / "bot" / "security.py").read_text(encoding="utf-8")

    assert "telegram_command_settings_submitted" in telegram_html
    assert "telegram_command_toggles" in telegram_html
    assert "/{{ toggle.command }}" in telegram_html
    assert "telegram_commands_enabled" in telegram_route
    assert "telegram_command_setting_key(command)" in telegram_route
    assert "is_telegram_command_enabled" in security_py
    assert "_telegram_command_name" in security_py
