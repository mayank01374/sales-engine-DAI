from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..db import get_db
from ..services import (
    STATUSES,
    create_or_update_opportunity,
    enrich_opportunity,
    export_csv,
    find_signals,
    import_csv,
    ingest_courtlistener,
    log_activity,
    run_research_task,
    score_opportunity,
)
from ..services import active_config

router = APIRouter()


@router.get("/api/opportunities", response_model=schemas.OpportunityListResponse)
def list_opportunities(
    db: Session = Depends(get_db),
    search: str | None = None,
    status: str | None = None,
    trigger_type: str | None = None,
    case_type: str | None = None,
    min_score: float | None = None,
    enrichment_status: str | None = None,
    has_law_firms: bool | None = None,
    sort_by: str = "final_trigger_score",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 50,
):
    q = db.query(models.Opportunity).options(joinedload(models.Opportunity.evidence))
    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                models.Opportunity.case_name.ilike(like),
                models.Opportunity.summary.ilike(like),
                models.Opportunity.notes.ilike(like),
            )
        )
    if status:
        q = q.filter(models.Opportunity.status == status)
    if trigger_type:
        q = q.filter(models.Opportunity.trigger_type.ilike(f"%{trigger_type}%"))
    if case_type:
        q = q.filter(models.Opportunity.case_type.ilike(f"%{case_type}%"))
    if min_score is not None:
        q = q.filter(models.Opportunity.final_trigger_score >= min_score)
    if enrichment_status:
        q = q.filter(models.Opportunity.enrichment_status == enrichment_status)
    if has_law_firms:
        q = q.join(models.Opportunity.law_firm_entities).distinct()
    total = q.count()
    col = getattr(models.Opportunity, sort_by, models.Opportunity.final_trigger_score)
    q = q.order_by(col.asc() if sort_dir == "asc" else col.desc())
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/api/opportunities/{opportunity_id}", response_model=schemas.OpportunityOut)
def get_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    opportunity = (
        db.query(models.Opportunity)
        .options(joinedload(models.Opportunity.evidence))
        .filter_by(id=opportunity_id)
        .first()
    )
    if not opportunity:
        raise HTTPException(404, "Opportunity not found")
    return opportunity


@router.post("/api/opportunities", response_model=schemas.OpportunityOut)
def create_opportunity(payload: schemas.OpportunityCreate, db: Session = Depends(get_db)):
    opp = create_or_update_opportunity(db, payload.model_dump())
    db.commit()
    db.refresh(opp)
    return opp


@router.patch("/api/opportunities/{opportunity_id}/status", response_model=schemas.OpportunityOut)
def update_status(
    opportunity_id: int,
    payload: schemas.StatusUpdate,
    db: Session = Depends(get_db),
):
    if payload.status not in STATUSES:
        raise HTTPException(400, "Invalid status")
    opp = db.get(models.Opportunity, opportunity_id)
    if not opp:
        raise HTTPException(404, "Opportunity not found")
    old = opp.status
    opp.status = payload.status
    log_activity(
        db,
        opp.id,
        "status_changed",
        f"Status changed from {old} to {payload.status}",
        actor_name="Sales",
    )
    db.commit()
    db.refresh(opp)
    return opp


@router.patch("/api/opportunities/{opportunity_id}/notes", response_model=schemas.OpportunityOut)
def update_notes(
    opportunity_id: int,
    payload: schemas.NotesUpdate,
    db: Session = Depends(get_db),
):
    opp = db.get(models.Opportunity, opportunity_id)
    if not opp:
        raise HTTPException(404, "Opportunity not found")
    opp.notes = payload.notes
    log_activity(db, opp.id, "notes_updated", "Updated notes", actor_name="Sales")
    db.commit()
    db.refresh(opp)
    return opp


@router.get("/api/opportunities/{opportunity_id}/evidence", response_model=list[schemas.EvidenceOut])
def evidence(opportunity_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.SourceEvidence)
        .filter_by(opportunity_id=opportunity_id)
        .order_by(models.SourceEvidence.created_at.desc())
        .all()
    )


@router.post("/api/opportunities/{opportunity_id}/enrich", response_model=list[schemas.AccountOut])
def enrich(opportunity_id: int, db: Session = Depends(get_db)):
    opp = (
        db.query(models.Opportunity)
        .options(joinedload(models.Opportunity.enriched_accounts))
        .filter_by(id=opportunity_id)
        .first()
    )
    if not opp:
        raise HTTPException(404, "Opportunity not found")
    enrich_opportunity(db, opp)
    db.commit()
    return (
        db.query(models.EnrichedAccount)
        .options(joinedload(models.EnrichedAccount.contacts))
        .filter_by(opportunity_id=opportunity_id)
        .all()
    )


@router.get("/api/opportunities/{opportunity_id}/enrichment", response_model=list[schemas.AccountOut])
def get_enrichment(opportunity_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.EnrichedAccount)
        .options(joinedload(models.EnrichedAccount.contacts))
        .filter_by(opportunity_id=opportunity_id)
        .all()
    )


@router.get("/api/enriched-accounts", response_model=list[schemas.AccountOut])
def get_accounts(db: Session = Depends(get_db)):
    return (
        db.query(models.EnrichedAccount)
        .options(joinedload(models.EnrichedAccount.contacts))
        .limit(200)
        .all()
    )


@router.post("/api/opportunities/{opportunity_id}/research-tasks", response_model=schemas.ResearchTaskOut)
def create_research_task(
    opportunity_id: int,
    payload: schemas.ResearchTaskCreate,
    db: Session = Depends(get_db),
):
    opp = db.get(models.Opportunity, opportunity_id)
    if not opp:
        raise HTTPException(404, "Opportunity not found")
    try:
        task = run_research_task(db, opp, payload.task_type)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(task)
    return task


@router.get("/api/opportunities/{opportunity_id}/research-tasks", response_model=list[schemas.ResearchTaskOut])
def get_research_tasks(opportunity_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.ResearchTask)
        .filter_by(opportunity_id=opportunity_id)
        .order_by(models.ResearchTask.created_at.desc())
        .all()
    )


@router.get("/api/opportunities/{opportunity_id}/activity", response_model=list[schemas.ActivityOut])
def get_activity(opportunity_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.OpportunityActivity)
        .filter_by(opportunity_id=opportunity_id)
        .order_by(models.OpportunityActivity.created_at.desc())
        .all()
    )


@router.post("/api/opportunities/rescore")
def rescore(db: Session = Depends(get_db)):
    cfg = active_config(db)
    count = 0
    for opp in db.query(models.Opportunity).all():
        old = opp.score
        score_opportunity(opp, cfg)
        count += 1
        if old != opp.score:
            log_activity(
                db,
                opp.id,
                "score_changed",
                f"Score changed from {old} to {opp.score}",
            )
    db.commit()
    return {"rescored": count}


@router.get("/api/opportunities/export.csv")
def export(db: Session = Depends(get_db)):
    return Response(
        content=export_csv(db),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=decoverAI-opportunities.csv"},
    )


@router.post("/api/opportunities/import.csv")
async def import_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    return import_csv(db, content)


@router.post("/api/ingest/find")
def find(db: Session = Depends(get_db)):
    return find_signals(db)


@router.post("/api/ingest/courtlistener")
def ingest_from_courtlistener(
    query: str = "antitrust OR trade secret OR data breach OR securities class action",
    page_size: int = 10,
    db: Session = Depends(get_db),
):
    try:
        return ingest_courtlistener(db, query=query, page_size=page_size)
    except Exception as e:
        raise HTTPException(502, f"CourtListener ingestion failed: {e}")
