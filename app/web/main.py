"""
FastAPI application — web interface with Jinja2 templates.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.database import init_db, engine
from app.scheduler import start_scheduler, stop_scheduler
from app.csrf import CsrfMiddleware
from app.utils import payment_color_class
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

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount uploads
import os
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Apply shared template globals to legacy route-local template engines.
configure_route_templates((auth, dashboard, payments, history, contractors, analytics, backups))

# Backward compatibility for payments.py context until the route is fully refactored.
payments.payment_color_class = payment_color_class


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

# CSRF middleware (after routers so that exempt paths like /login work)
app.add_middleware(CsrfMiddleware)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
