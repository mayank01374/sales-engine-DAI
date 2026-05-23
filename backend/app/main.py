from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .db import SessionLocal
from .errors import (
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from .routers import campaigns, discovery_signals, opportunities, settings as settings_router
from .services import seed

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("decoverai-signal")

app = FastAPI(title="decoverAI Signal Workspace API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

app.include_router(settings_router.router)
app.include_router(opportunities.router)
app.include_router(discovery_signals.router)
app.include_router(campaigns.router)


@app.on_event("startup")
def startup():
    db = SessionLocal()
    try:
        seed(db)
    except Exception:
        logger.exception("Database seeding failed")
        db.rollback()
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}
