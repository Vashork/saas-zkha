"""Tests for shared Jinja template configuration."""

from pathlib import Path
from types import SimpleNamespace

from fastapi.templating import Jinja2Templates

from app.csrf import CSRF_COOKIE
from app.web.routes import auth, payments
from app.web.template_engine import TEMPLATE_GLOBALS, configure_route_templates, configure_templates, templates


ROOT = Path(__file__).resolve().parents[1]


def test_template_globals_include_csrf_cookie_name():
    assert TEMPLATE_GLOBALS["csrf_cookie_name"] == CSRF_COOKIE


def test_template_globals_include_default_user_theme():
    assert TEMPLATE_GLOBALS["user_theme"] == "dark"


def test_configure_templates_adds_shared_globals(tmp_path):
    engine = Jinja2Templates(directory=str(tmp_path))

    result = configure_templates(engine)

    assert result is engine
    assert engine.env.globals["csrf_cookie_name"] == CSRF_COOKIE
    assert engine.env.globals["user_theme"] == "dark"


def test_configure_route_templates_updates_modules_with_templates(tmp_path):
    engine = Jinja2Templates(directory=str(tmp_path))
    route_module = SimpleNamespace(templates=engine)

    configure_route_templates((route_module, SimpleNamespace()))

    assert engine.env.globals["csrf_cookie_name"] == CSRF_COOKIE
    assert engine.env.globals["user_theme"] == "dark"


def test_auth_route_uses_shared_template_engine():
    assert auth.templates is templates


def test_payments_route_uses_shared_template_engine():
    assert payments.templates is templates


def test_main_no_longer_has_payments_template_workaround():
    main_source = (ROOT / "app" / "web" / "main.py").read_text(encoding="utf-8")

    assert "payments.payment_color_class" not in main_source
    assert "Backward compatibility for payments.py" not in main_source
