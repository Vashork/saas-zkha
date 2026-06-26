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


def test_form_controls_css_hides_number_input_spinners():
    form_controls_css = (ROOT / "app" / "web" / "static" / "css" / "form-controls.css").read_text(encoding="utf-8")

    assert 'input[type="number"].input-custom' in form_controls_css
    assert '::-webkit-inner-spin-button' in form_controls_css
    assert '-moz-appearance: textfield' in form_controls_css


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
