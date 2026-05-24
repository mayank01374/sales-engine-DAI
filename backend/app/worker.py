from __future__ import annotations

import os

from celery import Celery
from celery.exceptions import MaxRetriesExceededError
import httpx

from . import models
from .db import SessionLocal
from .services.web_discovery.runner import run_discovery

broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", broker_url)

celery_app = Celery("decoverai", broker=broker_url, backend=result_backend)

RETRYABLE_EXCEPTIONS = (
    httpx.HTTPError,
    TimeoutError,
    ConnectionError,
    OSError,
)


@celery_app.task(bind=True, name="web_discovery.run", max_retries=3)
def run_web_discovery_task(self, run_id: int, payload: dict):
    db = SessionLocal()
    try:
        run_discovery(db, existing_run_id=run_id, raise_on_failure=True, **payload)
    except Exception as exc:
        db.rollback()
        run = db.get(models.WebDiscoveryRun, run_id)
        can_retry = isinstance(exc, RETRYABLE_EXCEPTIONS) and self.request.retries < self.max_retries
        if run and can_retry:
            countdown = min(300, 2 ** self.request.retries * 10)
            run.status = "running"
            run.error_message = f"Transient discovery error; retrying in {countdown}s: {exc}"
            db.commit()
            db.close()
            try:
                raise self.retry(exc=exc, countdown=countdown)
            except MaxRetriesExceededError:
                db = SessionLocal()
                run = db.get(models.WebDiscoveryRun, run_id)
        if run:
            run.status = "failed"
            run.error_message = str(exc)
            db.commit()
        raise
    finally:
        db.close()
