"""
FastAPI application — web interface with Jinja2 templates.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.database import init_db, engine, async_session_factory
from app.scheduler import start_scheduler, stop_scheduler, scheduler
from app.csrf import CsrfMiddleware
from app.web.template_engine import configure_route_templates
from app.web.routes import auth, dashboard, payments, history, contractors, analytics, backups

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("zhkh.web")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "web" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("Initializing database...")
    await init_db()

    logger.info("Starting scheduler...")
    start_scheduler()

    yield

    logger.info("Shutting down...")
    stop_scheduler()
    await engine.dispose()


app = FastAPI(title="ZhKH Bot", lifespan=lifespan)

# Public static assets only. Receipts in data/uploads are served through
# authenticated routes such as /payments/receipts/{path}.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Apply shared template globals to remaining legacy route-local template engines.
configure_route_templates((auth, dashboard, payments, history, contractors, analytics, backups))


@app.middleware("http")
async def enforce_page_permissions(request: Request, call_next):
    """Close known route guard gaps while legacy routes are being refactored."""
    if request.method.upper() == "GET" and request.url.path == "/settings":
        redirect = await auth._require_page(request, "settings")
        if redirect:
            return redirect
    return await call_next(request)


# Include routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(payments.router)
app.include_router(history.router)
app.include_router(contractors.router)
app.include_router(analytics.router)
app.include_router(backups.router)

# CSRF middleware (after routers; safe methods issue tokens, unsafe methods verify them)
app.add_middleware(CsrfMiddleware)


@app.get("/health")
async def health_check(response: Response):
    """Return process, database and scheduler health."""
    health = {
        "status": "ok",
        "database": "ok",
        "scheduler": "running" if scheduler.running else "stopped",
    }

    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check database ping failed")
        health["status"] = "degraded"
        health["database"] = "error"
        response.status_code = 500

    return health
