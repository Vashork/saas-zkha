"""
FastAPI application — web interface with Jinja2 templates.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from app.database import init_db, engine
from app.scheduler import start_scheduler, stop_scheduler
from app.web.routes import auth, dashboard, payments, history, contractors, analytics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("zhkh.web")

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "web" / "templates"
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

# Include routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(payments.router)
app.include_router(history.router)
app.include_router(contractors.router)
app.include_router(analytics.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
