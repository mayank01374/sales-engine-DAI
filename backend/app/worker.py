from __future__ import annotations

import os

from celery import Celery

from . import models
from .db import SessionLocal
from .services.web_discovery.runner import run_discovery

broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", broker_url)

celery_app = Celery("decoverai", broker=broker_url, backend=result_backend)


@celery_app.task(name="web_discovery.run")
def run_web_discovery_task(run_id: int, payload: dict):
    db = SessionLocal()
    try:
        run_discovery(db, existing_run_id=run_id, **payload)
    except Exception as exc:
        db.rollback()
        run = db.get(models.WebDiscoveryRun, run_id)
        if run:
            run.status = "failed"
            run.error_message = str(exc)
            db.commit()
        raise
    finally:
        db.close()
