"""Tests for shared Jinja template configuration."""

from types import SimpleNamespace

from fastapi.templating import Jinja2Templates

from app.csrf import CSRF_COOKIE
from app.web.template_engine import TEMPLATE_GLOBALS, configure_route_templates, configure_templates


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
