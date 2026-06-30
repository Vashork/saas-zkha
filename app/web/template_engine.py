"""Shared Jinja template configuration for the web UI."""

from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates as _BaseJinja2Templates

from app.csrf import CSRF_COOKIE

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "web" / "templates"

TEMPLATE_GLOBALS = {
    "user_theme": "dark",
    "csrf_cookie_name": CSRF_COOKIE,
}


class CompatJinja2Templates(_BaseJinja2Templates):
    """Compatibility adapter for Starlette 1.x template responses.

    Starlette 1.0 removed the deprecated ``TemplateResponse(name, context)``
    signature. Existing routes still use that legacy shape, with ``request``
    stored in the context. Keep those calls working while preserving the new
    ``TemplateResponse(request, name, ...)`` signature for future route code.
    """

    def TemplateResponse(self, *args: Any, **kwargs: Any):  # noqa: N802 - Starlette API name
        if args and isinstance(args[0], str):
            name = args[0]
            context = args[1] if len(args) > 1 else kwargs.pop("context", None)
            if not isinstance(context, dict):
                return super().TemplateResponse(*args, **kwargs)

            request = context.get("request")
            if request is None:
                return super().TemplateResponse(*args, **kwargs)

            return super().TemplateResponse(request, name, context, *args[2:], **kwargs)

        return super().TemplateResponse(*args, **kwargs)


Jinja2Templates = CompatJinja2Templates


def configure_templates(template_engine: Jinja2Templates) -> Jinja2Templates:
    template_engine.env.globals.update(TEMPLATE_GLOBALS)
    return template_engine


templates = configure_templates(Jinja2Templates(directory=str(TEMPLATES_DIR)))


def configure_route_templates(route_modules) -> None:
    for route_module in route_modules:
        route_templates = getattr(route_module, "templates", None)
        if route_templates is not None:
            configure_templates(route_templates)
