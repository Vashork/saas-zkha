"""Tests for DB-backed Telegram response templates and handler wiring."""

from pathlib import Path

import pytest

from app.bot.response_templates import (
    DEFAULT_TELEGRAM_RESPONSE_TEMPLATES,
    MANAGED_TELEGRAM_RESPONSE_TEMPLATES,
    TelegramTemplateValidationError,
    extract_template_placeholders,
    render_template_text,
    telegram_response_template_definitions,
    telegram_template_setting_key,
    validate_template_placeholders,
)

ROOT = Path(__file__).resolve().parents[1]


def test_default_template_names_and_setting_keys_are_stable():
    names = tuple(MANAGED_TELEGRAM_RESPONSE_TEMPLATES)
    definitions = telegram_response_template_definitions()

    assert names == (
        "start",
        "help",
        "error_invalid_payment_format",
        "error_invalid_receipt_file",
        "payment_confirmation",
    )
    assert tuple(item.name for item in definitions) == names
    assert set(DEFAULT_TELEGRAM_RESPONSE_TEMPLATES) == set(names)
    assert [item.setting_key for item in definitions] == [
        telegram_template_setting_key(name) for name in names
    ]
    assert telegram_template_setting_key("start") == "telegram_template_start"


def test_placeholder_extraction_uses_single_brace_names_only():
    template = "{amount} {{ignored}} {contractor_name} {period} {bad-name} {x1}"

    assert extract_template_placeholders(template) == {
        "amount",
        "contractor_name",
        "period",
        "x1",
    }


def test_invalid_placeholder_rejected_for_non_payment_template():
    with pytest.raises(TelegramTemplateValidationError):
        validate_template_placeholders("help", "Help for {contractor_name}")


def test_valid_payment_confirmation_rendering():
    rendered = render_template_text(
        "payment_confirmation",
        "✅ <b>{contractor_name}</b> {amount} {period}{receipt_saved_line}",
        {
            "contractor_name": "Мосэнергосбыт",
            "amount": "3200",
            "period": "июнь 2026",
            "receipt_saved_line": "\n📎 Чек сохранён",
        },
    )

    assert rendered == "✅ <b>Мосэнергосбыт</b> 3200 июнь 2026\n📎 Чек сохранён"


def test_unknown_payment_confirmation_placeholder_is_rejected():
    with pytest.raises(TelegramTemplateValidationError):
        render_template_text("payment_confirmation", "{amount} {unsafe}", {"amount": "1"})


def test_telegram_handler_source_wires_managed_templates():
    handlers_py = (ROOT / "app" / "bot" / "handlers.py").read_text(encoding="utf-8")

    assert "render_telegram_response_template" in handlers_py
    assert '_response_template("start")' in handlers_py
    assert '_response_template("help")' in handlers_py
    assert '_response_template("error_invalid_payment_format")' in handlers_py
    assert '"error_invalid_receipt_file"' in handlers_py
    assert '"payment_confirmation"' in handlers_py
    assert 'html.escape(str(contractor.name))' in handlers_py
    assert '"receipt_saved_line": "\\n📎 Чек сохранён" if receipt_path else ""' in handlers_py
