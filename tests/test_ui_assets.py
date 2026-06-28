"""UI asset wiring tests."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_base_loads_form_controls_css_after_main_stylesheet():
    base_html = (ROOT / "app" / "web" / "templates" / "base.html").read_text(encoding="utf-8")

    style_pos = base_html.index('/static/css/style.css')
    form_controls_pos = base_html.index('/static/css/form-controls.css')

    assert style_pos < form_controls_pos


def test_base_loads_modal_css_after_main_stylesheet():
    base_html = (ROOT / "app" / "web" / "templates" / "base.html").read_text(encoding="utf-8")

    style_pos = base_html.index('/static/css/style.css')
    modal_pos = base_html.index('/static/css/modal.css')

    assert style_pos < modal_pos


def test_form_controls_css_keeps_number_input_steppers_visible_and_themed():
    form_controls_css = (ROOT / "app" / "web" / "static" / "css" / "form-controls.css").read_text(encoding="utf-8")

    assert 'input[type="number"].input-custom' in form_controls_css
    assert 'color-scheme: dark' in form_controls_css
    assert '::-webkit-inner-spin-button' not in form_controls_css
    assert '-moz-appearance: textfield' not in form_controls_css


def test_modal_css_contains_add_payment_modal_helpers():
    modal_css = (ROOT / "app" / "web" / "static" / "css" / "modal.css").read_text(encoding="utf-8")

    assert ".modal-card-wide" in modal_css
    assert ".modal-card-scroll" in modal_css
    assert "overflow-y: auto" in modal_css


def test_payments_template_uses_add_payment_modal():
    payments_html = (ROOT / "app" / "web" / "templates" / "payments.html").read_text(encoding="utf-8")

    assert 'id="addPaymentModal"' in payments_html
    assert 'openAddPaymentModal()' in payments_html
    assert 'action="/payments/add"' in payments_html


def test_payments_template_warns_about_partial_fixed_payment():
    payments_html = (ROOT / "app" / "web" / "templates" / "payments.html").read_text(encoding="utf-8")

    assert "сумму меньше фиксированной" in payments_html
    assert "остаток будет показан как долг" in payments_html


def test_receipt_link_is_visible_before_paid_only_upload_button():
    payments_html = (ROOT / "app" / "web" / "templates" / "payments.html").read_text(encoding="utf-8")

    receipt_condition_pos = payments_html.index("{% if p.receipt_file and not p.transactions %}")
    status_condition_pos = payments_html.index("{% if current_status == 'paid' %}")

    assert receipt_condition_pos < status_condition_pos


def test_payments_template_has_partial_payment_modal_and_route():
    payments_html = (ROOT / "app" / "web" / "templates" / "payments.html").read_text(encoding="utf-8")

    assert 'id="transactionModal"' in payments_html
    assert 'openTransactionModal(' in payments_html
    assert "/transactions/add" in payments_html
    assert "Частично" in payments_html
    assert "Частично просрочено" in payments_html


def test_payments_template_allows_variable_payment_top_ups():
    payments_html = (ROOT / "app" / "web" / "templates" / "payments.html").read_text(encoding="utf-8")

    assert "p.contractor.payment_type == 'variable'" in payments_html
    assert "сумма сверх остатка увеличит начисление" in payments_html
    assert 'id="transactionHint"' in payments_html


def test_payments_template_renders_transaction_receipts():
    payments_html = (ROOT / "app" / "web" / "templates" / "payments.html").read_text(encoding="utf-8")

    assert "{% for tx in p.transactions %}" in payments_html
    assert "tx.receipt_file" in payments_html
    assert "Скачать чек оплаты" in payments_html


def test_payments_template_has_transaction_edit_and_delete_actions():
    payments_html = (ROOT / "app" / "web" / "templates" / "payments.html").read_text(encoding="utf-8")

    assert 'id="transactionEditModal"' in payments_html
    assert 'openTransactionEditModal(' in payments_html
    assert '/payments/transactions/{{ tx.id }}/delete' in payments_html
    assert '/payments/transactions/' in payments_html
    assert "Редактировать оплату" in payments_html


def test_backups_template_formats_timestamps_with_configured_timezone():
    backups_html = (ROOT / "app" / "web" / "templates" / "backups.html").read_text(encoding="utf-8")
    backups_route = (ROOT / "app" / "web" / "routes" / "backups.py").read_text(encoding="utf-8")

    assert "backup_timezone" in backups_html
    assert "format_datetime(f.created_at, backup_timezone)" in backups_html
    assert "format_datetime(item.created_at, backup_timezone)" in backups_html
    assert "SQLite connections" in backups_route


def test_backups_template_has_mounted_remote_backup_settings():
    backups_html = (ROOT / "app" / "web" / "templates" / "backups.html").read_text(encoding="utf-8")

    assert "Mounted share" in backups_html
    assert 'name="backup_destination_local"' in backups_html
    assert 'name="backup_destination_remote"' in backups_html
    assert 'name="backup_remote_type"' in backups_html
    assert 'name="backup_remote_path"' in backups_html
    assert 'name="backup_keep_local_copy"' in backups_html
    assert "/mnt/zhkh-backups" in backups_html
    assert "смонтированную папку" in backups_html
    assert "Не указывайте" in backups_html
