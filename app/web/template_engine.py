"""Shared Jinja template configuration for the web UI."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.csrf import CSRF_COOKIE

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "web" / "templates"

TEMPLATE_GLOBALS = {
    "user_theme": "dark",
    "csrf_cookie_name": CSRF_COOKIE,
}


def configure_templates(template_engine: Jinja2Templates) -> Jinja2Templates:
    template_engine.env.globals.update(TEMPLATE_GLOBALS)
    return template_engine


templates = configure_templates(Jinja2Templates(directory=str(TEMPLATES_DIR)))


def configure_route_templates(route_modules) -> None:
    for route_module in route_modules:
        route_templates = getattr(route_module, "templates", None)
        if route_templates is not None:
            configure_templates(route_templates)
