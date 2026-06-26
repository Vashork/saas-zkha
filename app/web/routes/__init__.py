"""Routes package."""

# Load route-level compatibility fixes before app.web.main includes routers.
from app.web.routes import payment_edit_patch  # noqa: F401,E402
