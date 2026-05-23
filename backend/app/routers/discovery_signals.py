from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..db import get_db
from ..services import active_config
from ..services.web_discovery.query_builder import build_discovery_queries
from ..services.web_discovery.quality import apply_quality_to_signal
from ..services.web_discovery.runner import convert_signal_to_opportunity
from ..services.web_discovery.source_packs import enabled_source_packs
from ..worker import run_web_discovery_task

router = APIRouter()


@router.get("/api/daily-triggers", response_model=schemas.DailyTriggerResponse)
def daily_triggers(
    db: Session = Depends(get_db),
    limit: int | None = None,
    matter_type: str | None = None,
    trigger_category: str | None = None,
    min_source_quality: float | None = None,
    min_score: float | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int | None = None,
):
    cfg = active_config(db)
    page_size = max(
        1,
        min(
            page_size or limit or cfg.max_daily_triggers or 50,
            cfg.max_daily_triggers or 50,
            50,
        ),
    )
    q = (
        db.query(models.DiscoveredSignal)
        .options(joinedload(models.DiscoveredSignal.scrape_attempts))
        .filter(
            models.DiscoveredSignal.gate_passed == True,
            models.DiscoveredSignal.freshness_status != "stale",
            models.DiscoveredSignal.status != "rejected",
            models.DiscoveredSignal.duplicate_of_opportunity_id.is_(None),
        )
    )
    if matter_type:
        q = q.filter(models.DiscoveredSignal.matter_type.ilike(f"%{matter_type}%"))
    if trigger_category:
        q = q.filter(models.DiscoveredSignal.trigger_category.ilike(f"%{trigger_category}%"))
    if min_source_quality is not None:
        q = q.filter(models.DiscoveredSignal.source_quality_score >= min_source_quality)
    if min_score is not None:
        q = q.filter(models.DiscoveredSignal.final_trigger_score >= min_score)
    if status:
        q = q.filter(models.DiscoveredSignal.status == status)
    if date_from:
        q = q.filter(models.DiscoveredSignal.published_at >= date_from)
    if date_to:
        q = q.filter(models.DiscoveredSignal.published_at <= date_to)
    candidates = (
        q.order_by(
            models.DiscoveredSignal.source_tier.asc(),
            models.DiscoveredSignal.final_trigger_score.desc(),
            models.DiscoveredSignal.signal_age_days.asc().nullslast(),
            models.DiscoveredSignal.created_at.desc(),
        )
        .limit(200)
        .all()
    )
    domain_counts = {}
    category_counts = {}
    party_counts = {}
    items = []
    tier_weight = {
        "tier_1_court_docket": 0,
        "tier_1_litigation_alert": 1,
        "tier_2_legal_news": 2,
        "tier_2_law_firm": 2,
        "tier_3_regulator": 3,
        "tier_3_business_news": 4,
        "low_quality": 5,
    }
    candidates.sort(
        key=lambda signal: (
            tier_weight.get(signal.source_tier or "", 6),
            -(signal.final_trigger_score or 0),
            signal.signal_age_days if signal.signal_age_days is not None else 9999,
        )
    )
    for signal in candidates:
        domain = signal.source_domain or "unknown"
        category = signal.trigger_category or signal.trigger_type or "unknown"
        party_key = "|".join(sorted((signal.parties or [])[:2])) or signal.title[:80]
        if domain_counts.get(domain, 0) >= (cfg.max_per_source_domain or 4):
            continue
        if category_counts.get(category, 0) >= (cfg.max_per_trigger_category or 5):
            continue
        if party_counts.get(party_key, 0) >= (cfg.max_per_same_party or 2):
            continue
        items.append(signal)
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1
        party_counts[party_key] = party_counts.get(party_key, 0) + 1
        if len(items) >= page_size:
            break
    total = len(candidates)
    items = items[(page - 1) * page_size : page * page_size]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/api/daily-triggers/export.csv")
def export_daily_triggers(
    db: Session = Depends(get_db),
    matter_type: str | None = None,
    trigger_category: str | None = None,
    min_source_quality: float | None = None,
    min_score: float | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    data = daily_triggers(
        db=db,
        matter_type=matter_type,
        trigger_category=trigger_category,
        min_source_quality=min_source_quality,
        min_score=min_score,
        status=status,
        date_from=date_from,
        date_to=date_to,
        page=1,
        page_size=50,
    )
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "id",
            "final_score",
            "gate",
            "status",
            "matter",
            "parties",
            "matter_type",
            "trigger",
            "source",
            "freshness",
            "source_quality",
            "discovery_pain",
            "fit",
            "persona",
            "sales_angle",
            "why_now",
            "discovery_pain_summary",
        ]
    )
    for signal in data["items"]:
        writer.writerow(
            [
                signal.id,
                round(signal.final_trigger_score or 0, 1),
                signal.gate_status or ("passed" if signal.gate_passed else "failed"),
                signal.status,
                signal.title,
                "; ".join(signal.parties or []),
                signal.matter_type or signal.case_type,
                signal.trigger_category or signal.trigger_type,
                signal.source_url,
                signal.freshness_status,
                round(signal.source_quality_score or 0, 1),
                round(signal.discovery_pain_score or 0, 1),
                round(signal.dcover_fit_score or 0, 1),
                "; ".join(signal.recommended_personas or []),
                signal.sales_angle_one_liner,
                signal.why_now,
                signal.discovery_pain_summary,
            ]
        )
    return Response(
        content=out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=daily-triggers.csv"},
    )


@router.post("/api/web-discovery/runs", response_model=schemas.WebDiscoveryRunOut)
def create_web_discovery_run(
    payload: schemas.WebDiscoveryRunCreate,
    db: Session = Depends(get_db),
):
    payload.trigger_type = payload.trigger_type or "all"
    cfg = active_config(db)
    queries = build_discovery_queries(
        payload.trigger_type,
        "US",
        "",
        enabled_source_packs(cfg.source_packs),
    )
    run = models.WebDiscoveryRun(
        query=" | ".join(queries),
        trigger_type=payload.trigger_type,
        geography="US",
        industry="",
        time_range=payload.time_range,
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background_payload = payload.model_dump()
    run_web_discovery_task.delay(run.id, background_payload)
    return run


@router.get("/api/web-discovery/runs", response_model=list[schemas.WebDiscoveryRunOut])
def list_web_discovery_runs(db: Session = Depends(get_db)):
    return db.query(models.WebDiscoveryRun).order_by(models.WebDiscoveryRun.created_at.desc()).limit(100).all()


@router.get("/api/web-discovery/runs/{run_id}", response_model=schemas.WebDiscoveryRunOut)
def get_web_discovery_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(models.WebDiscoveryRun, run_id)
    if not run:
        raise HTTPException(404, "Web discovery run not found")
    return run


@router.get("/api/web-discovery/runs/{run_id}/signals", response_model=list[schemas.DiscoveredSignalOut])
def list_discovered_signals(
    run_id: int,
    tab: str = "all",
    page: int = 1,
    page_size: int = 100,
    db: Session = Depends(get_db),
):
    run = db.get(models.WebDiscoveryRun, run_id)
    if not run:
        raise HTTPException(404, "Web discovery run not found")
    q = (
        db.query(models.DiscoveredSignal)
        .options(joinedload(models.DiscoveredSignal.scrape_attempts))
        .filter_by(discovery_run_id=run_id)
    )
    if tab == "needs_review":
        q = q.filter(models.DiscoveredSignal.status.in_(["new", "reviewed"]))
    elif tab == "passed_gate":
        q = q.filter(models.DiscoveredSignal.gate_passed == True)
    elif tab == "failed_gate":
        q = q.filter(models.DiscoveredSignal.gate_passed == False)
    elif tab == "duplicates":
        q = q.filter(models.DiscoveredSignal.duplicate_of_opportunity_id.isnot(None))
    elif tab == "rejected":
        q = q.filter(models.DiscoveredSignal.status == "rejected")
    elif tab == "converted":
        q = q.filter(models.DiscoveredSignal.status == "converted")
    page_size = max(1, min(page_size, 200))
    return (
        q.order_by(
            models.DiscoveredSignal.final_trigger_score.desc(),
            models.DiscoveredSignal.created_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )


@router.get("/api/discovered-signals/{signal_id}", response_model=schemas.DiscoveredSignalDetailOut)
def get_discovered_signal(signal_id: int, db: Session = Depends(get_db)):
    signal = (
        db.query(models.DiscoveredSignal)
        .options(joinedload(models.DiscoveredSignal.scrape_attempts))
        .filter_by(id=signal_id)
        .first()
    )
    if not signal:
        raise HTTPException(404, "Discovered signal not found")
    return signal


@router.patch("/api/discovered-signals/{signal_id}/status", response_model=schemas.DiscoveredSignalOut)
def update_discovered_signal_status(
    signal_id: int,
    payload: schemas.DiscoveredSignalStatusUpdate,
    db: Session = Depends(get_db),
):
    signal = (
        db.query(models.DiscoveredSignal)
        .options(joinedload(models.DiscoveredSignal.scrape_attempts))
        .filter_by(id=signal_id)
        .first()
    )
    if not signal:
        raise HTTPException(404, "Discovered signal not found")
    signal.status = payload.status
    if payload.status == "rejected":
        signal.rejection_reason = payload.rejection_reason or "Rejected by sales review."
    apply_quality_to_signal(signal, db)
    db.commit()
    db.refresh(signal)
    return signal


@router.patch("/api/discovered-signals/{signal_id}/sales-review", response_model=schemas.DiscoveredSignalOut)
def update_discovered_signal_sales_review(
    signal_id: int,
    payload: schemas.SalesReviewUpdate,
    db: Session = Depends(get_db),
):
    signal = (
        db.query(models.DiscoveredSignal)
        .options(joinedload(models.DiscoveredSignal.scrape_attempts))
        .filter_by(id=signal_id)
        .first()
    )
    if not signal:
        raise HTTPException(404, "Discovered signal not found")
    signal.sales_review_status = payload.review_status
    signal.sales_review_reason = payload.reason
    signal.sales_review_notes = payload.notes
    db.commit()
    db.refresh(signal)
    return signal


@router.post("/api/discovered-signals/{signal_id}/convert", response_model=schemas.OpportunityOut)
def convert_discovered_signal(signal_id: int, db: Session = Depends(get_db)):
    signal = (
        db.query(models.DiscoveredSignal)
        .options(joinedload(models.DiscoveredSignal.discovery_run))
        .filter_by(id=signal_id)
        .first()
    )
    if not signal:
        raise HTTPException(404, "Discovered signal not found")
    if signal.status == "rejected":
        raise HTTPException(400, "Rejected signals cannot be converted")
    try:
        opp = convert_signal_to_opportunity(db, signal)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    db.commit()
    return (
        db.query(models.Opportunity)
        .options(joinedload(models.Opportunity.evidence))
        .filter_by(id=opp.id)
        .first()
    )
