from __future__ import annotations
import logging
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func, inspect, text
from .config import settings
from .db import Base, engine, get_db, SessionLocal
from . import models, schemas
from .errors import http_exception_handler, validation_exception_handler, generic_exception_handler
from .services import seed, create_or_update_opportunity, score_opportunity, active_config, enrich_opportunity, run_research_task, export_csv, import_csv, log_activity, source_registry, ingest_courtlistener, find_signals, STATUSES
from .services.web_discovery.query_builder import build_discovery_queries
from .services.web_discovery.runner import run_discovery, convert_signal_to_opportunity
from .services.web_discovery.quality import apply_quality_to_signal, quality_gate, safe_score
from .services.web_discovery.source_packs import default_source_packs, enabled_source_packs
from .services.web_discovery.gemini_judge import check_gemini

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("decoverai-signal")

app = FastAPI(title="decoverAI Signal Workspace API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

def ensure_lightweight_columns():
    column_defs = {
        "opportunities": {
            "matter_type": "VARCHAR(160)", "trigger_category": "VARCHAR(160)", "party_roles": "JSON",
            "court_or_regulator": "VARCHAR(300)", "jurisdiction": "VARCHAR(160)", "factual_basis": "TEXT",
            "discovery_pain_summary": "TEXT", "why_now": "TEXT", "why_decoverai": "TEXT",
            "recommended_personas": "JSON", "sales_angle_one_liner": "TEXT", "email_subject": "VARCHAR(300)",
            "email_body": "TEXT", "linkedin_message": "TEXT", "call_opener": "TEXT",
            "confidence_score": "FLOAT", "source_quality_score": "FLOAT", "discovery_pain_score": "FLOAT",
            "dcover_fit_score": "FLOAT", "sales_actionability_score": "FLOAT", "final_trigger_score": "FLOAT",
            "extraction_warnings": "JSON", "missing_fields": "JSON",
            "is_litigation_trigger": "BOOLEAN", "trigger_relevance_reason": "TEXT",
            "gate_status": "VARCHAR(40)", "gate_failure_reasons": "JSON", "duplicate_confidence": "FLOAT",
            "source_tier": "VARCHAR(80)", "source_reason": "TEXT",
        },
        "source_evidence": {
            "source_tier": "VARCHAR(80)", "source_reason": "TEXT",
        },
        "discovered_signals": {
            "matter_type": "VARCHAR(160)", "trigger_category": "VARCHAR(160)", "party_roles": "JSON",
            "court_or_regulator": "VARCHAR(300)", "jurisdiction": "VARCHAR(160)", "factual_basis": "TEXT",
            "discovery_pain_summary": "TEXT", "why_now": "TEXT", "why_decoverai": "TEXT",
            "recommended_personas": "JSON", "sales_angle_one_liner": "TEXT", "email_subject": "VARCHAR(300)",
            "email_body": "TEXT", "linkedin_message": "TEXT", "call_opener": "TEXT",
            "source_quality_score": "FLOAT", "discovery_pain_score": "FLOAT", "dcover_fit_score": "FLOAT",
            "sales_actionability_score": "FLOAT", "final_trigger_score": "FLOAT",
            "extraction_warnings": "JSON", "missing_fields": "JSON", "gate_passed": "BOOLEAN",
            "gate_reason": "TEXT", "rejection_reason": "TEXT", "duplicate_reason": "TEXT",
            "is_litigation_trigger": "BOOLEAN", "trigger_relevance_reason": "TEXT",
            "gate_status": "VARCHAR(40)", "gate_failure_reasons": "JSON", "duplicate_confidence": "FLOAT",
            "source_tier": "VARCHAR(80)", "source_reason": "TEXT",
            "signal_date": "TIMESTAMP WITH TIME ZONE", "signal_age_days": "INTEGER", "freshness_status": "VARCHAR(40)",
            "freshness_reason": "TEXT", "sales_action_plan": "JSON",
            "sales_review_status": "VARCHAR(40)", "sales_review_reason": "VARCHAR(80)", "sales_review_notes": "TEXT",
        },
        "scoring_config": {
            "confidence_weight": "FLOAT", "source_quality_weight": "FLOAT", "discovery_pain_quality_weight": "FLOAT",
            "dcover_fit_weight": "FLOAT", "sales_actionability_weight": "FLOAT", "final_trigger_threshold": "FLOAT",
            "min_confidence_score": "FLOAT", "min_source_quality_score": "FLOAT", "min_discovery_pain_score": "FLOAT",
            "min_dcover_fit_score": "FLOAT", "min_sales_actionability_score": "FLOAT",
            "max_daily_triggers": "INTEGER", "default_geography": "VARCHAR(120)",
            "default_industry": "VARCHAR(160)", "default_time_range": "VARCHAR(40)",
            "default_max_results": "INTEGER",
            "max_signal_age_days": "INTEGER", "allow_unknown_signal_date": "BOOLEAN",
            "max_per_source_domain": "INTEGER", "max_per_trigger_category": "INTEGER",
            "max_per_same_party": "INTEGER",
            "source_allowlist": "TEXT", "source_blocklist": "TEXT", "discovery_query_settings": "JSON",
            "source_packs": "JSON",
        },
    }
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, defs in column_defs.items():
            if table not in inspector.get_table_names():
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            for name, ddl in defs.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        if "discovered_signals" in inspector.get_table_names():
            conn.execute(text("UPDATE discovered_signals SET freshness_status = 'unknown' WHERE freshness_status IS NULL"))
            conn.execute(text("UPDATE discovered_signals SET freshness_reason = 'unknown_date' WHERE freshness_reason IS NULL"))
            conn.execute(text("UPDATE discovered_signals SET source_tier = 'low_quality' WHERE source_tier IS NULL"))
            conn.execute(text("UPDATE discovered_signals SET source_reason = '' WHERE source_reason IS NULL"))
            conn.execute(text("UPDATE discovered_signals SET sales_action_plan = '{}' WHERE sales_action_plan IS NULL"))
            conn.execute(text("UPDATE discovered_signals SET sales_review_status = '' WHERE sales_review_status IS NULL"))
            conn.execute(text("UPDATE discovered_signals SET sales_review_reason = '' WHERE sales_review_reason IS NULL"))
            conn.execute(text("UPDATE discovered_signals SET sales_review_notes = '' WHERE sales_review_notes IS NULL"))
        if "source_evidence" in inspector.get_table_names():
            conn.execute(text("UPDATE source_evidence SET source_tier = 'low_quality' WHERE source_tier IS NULL"))
            conn.execute(text("UPDATE source_evidence SET source_reason = '' WHERE source_reason IS NULL"))
        if "scoring_config" in inspector.get_table_names():
            conn.execute(text("UPDATE scoring_config SET final_trigger_threshold = 70 WHERE final_trigger_threshold IS NULL OR final_trigger_threshold >= 75"))
            conn.execute(text("UPDATE scoring_config SET min_confidence_score = 60 WHERE min_confidence_score IS NULL OR min_confidence_score >= 70"))
            conn.execute(text("UPDATE scoring_config SET min_source_quality_score = 50 WHERE min_source_quality_score IS NULL OR min_source_quality_score >= 65"))
            conn.execute(text("UPDATE scoring_config SET min_discovery_pain_score = 60 WHERE min_discovery_pain_score IS NULL OR min_discovery_pain_score >= 70"))
            conn.execute(text("UPDATE scoring_config SET min_dcover_fit_score = 60 WHERE min_dcover_fit_score IS NULL OR min_dcover_fit_score >= 70"))
            conn.execute(text("UPDATE scoring_config SET min_sales_actionability_score = 60 WHERE min_sales_actionability_score IS NULL OR min_sales_actionability_score >= 75"))
            conn.execute(text("UPDATE scoring_config SET max_daily_triggers = 50 WHERE max_daily_triggers IS NULL OR max_daily_triggers <= 20"))
            conn.execute(text("UPDATE scoring_config SET default_max_results = 40 WHERE default_max_results IS NULL OR default_max_results <= 20"))

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    ensure_lightweight_columns()
    db=SessionLocal()
    try: seed(db)
    finally: db.close()

@app.get("/health")
def health(): return {"status":"ok"}

def settings_from_config(cfg: models.ScoringConfig):
    return {
        "final_trigger_score_min": safe_score(cfg.final_trigger_threshold, 70),
        "confidence_score_min": safe_score(cfg.min_confidence_score, 60),
        "source_quality_score_min": safe_score(cfg.min_source_quality_score, 50),
        "discovery_pain_score_min": safe_score(cfg.min_discovery_pain_score, 60),
        "dcover_fit_score_min": safe_score(cfg.min_dcover_fit_score, 60),
        "max_daily_triggers": int(cfg.max_daily_triggers or 50),
        "max_signal_age_days": int(cfg.max_signal_age_days or 90),
        "allow_unknown_signal_date": bool(cfg.allow_unknown_signal_date),
        "max_per_source_domain": int(cfg.max_per_source_domain or 4),
        "max_per_trigger_category": int(cfg.max_per_trigger_category or 5),
        "max_per_same_party": int(cfg.max_per_same_party or 2),
        "trusted_domains": cfg.source_allowlist or "",
        "blocked_domains": cfg.source_blocklist or "",
        "default_time_range": cfg.default_time_range or "week",
        "default_max_results": int(cfg.default_max_results or 40),
        "source_packs": cfg.source_packs or default_source_packs(),
        "enable_demo_data": settings.enable_demo_data,
    }

@app.get("/api/settings", response_model=schemas.SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return settings_from_config(active_config(db))

@app.put("/api/settings", response_model=schemas.SettingsOut)
def put_settings(payload: schemas.SettingsUpdate, db: Session = Depends(get_db)):
    cfg = active_config(db)
    cfg.final_trigger_threshold = safe_score(payload.final_trigger_score_min, 70)
    cfg.min_confidence_score = safe_score(payload.confidence_score_min, 60)
    cfg.min_source_quality_score = safe_score(payload.source_quality_score_min, 50)
    cfg.min_discovery_pain_score = safe_score(payload.discovery_pain_score_min, 60)
    cfg.min_dcover_fit_score = safe_score(payload.dcover_fit_score_min, 60)
    cfg.max_daily_triggers = max(1, min(int(payload.max_daily_triggers or 50), 50))
    cfg.max_signal_age_days = max(1, min(int(payload.max_signal_age_days or 90), 730))
    cfg.allow_unknown_signal_date = bool(payload.allow_unknown_signal_date)
    cfg.max_per_source_domain = max(1, min(int(payload.max_per_source_domain or 4), 20))
    cfg.max_per_trigger_category = max(1, min(int(payload.max_per_trigger_category or 5), 20))
    cfg.max_per_same_party = max(1, min(int(payload.max_per_same_party or 2), 20))
    cfg.source_allowlist = payload.trusted_domains
    cfg.source_blocklist = payload.blocked_domains
    cfg.default_time_range = payload.default_time_range
    cfg.default_max_results = payload.default_max_results
    cfg.source_packs = payload.source_packs or default_source_packs()
    db.commit(); db.refresh(cfg)
    return settings_from_config(cfg)

@app.get("/api/opportunities", response_model=schemas.OpportunityListResponse)
def list_opportunities(db: Session=Depends(get_db), search: str|None=None, status: str|None=None, trigger_type: str|None=None, case_type: str|None=None, min_score: float|None=None, enrichment_status: str|None=None, has_law_firms: bool|None=None, sort_by: str="final_trigger_score", sort_dir: str="desc", page:int=1, page_size:int=50):
    q=db.query(models.Opportunity).options(joinedload(models.Opportunity.evidence))
    if search:
        like=f"%{search}%"; q=q.filter(or_(models.Opportunity.case_name.ilike(like), models.Opportunity.summary.ilike(like), models.Opportunity.notes.ilike(like)))
    if status: q=q.filter(models.Opportunity.status==status)
    if trigger_type: q=q.filter(models.Opportunity.trigger_type.ilike(f"%{trigger_type}%"))
    if case_type: q=q.filter(models.Opportunity.case_type.ilike(f"%{case_type}%"))
    if min_score is not None: q=q.filter(models.Opportunity.final_trigger_score>=min_score)
    if enrichment_status: q=q.filter(models.Opportunity.enrichment_status==enrichment_status)
    if has_law_firms: q=q.filter(models.Opportunity.law_firms != [])
    total=q.count()
    col=getattr(models.Opportunity, sort_by, models.Opportunity.final_trigger_score)
    q=q.order_by(col.asc() if sort_dir=="asc" else col.desc())
    items=q.offset((page-1)*page_size).limit(page_size).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}

@app.get("/api/opportunities/{opportunity_id}", response_model=schemas.OpportunityOut)
def get_opportunity(opportunity_id:int, db:Session=Depends(get_db)):
    o=db.query(models.Opportunity).options(joinedload(models.Opportunity.evidence)).filter_by(id=opportunity_id).first()
    if not o: raise HTTPException(404,"Opportunity not found")
    return o

@app.post("/api/opportunities", response_model=schemas.OpportunityOut)
def create_opportunity(payload: schemas.OpportunityCreate, db:Session=Depends(get_db)):
    opp=create_or_update_opportunity(db, payload.model_dump())
    db.commit(); db.refresh(opp)
    return opp

@app.patch("/api/opportunities/{opportunity_id}/status", response_model=schemas.OpportunityOut)
def update_status(opportunity_id:int, payload:schemas.StatusUpdate, db:Session=Depends(get_db)):
    if payload.status not in STATUSES: raise HTTPException(400,"Invalid status")
    opp=db.get(models.Opportunity, opportunity_id)
    if not opp: raise HTTPException(404,"Opportunity not found")
    old=opp.status; opp.status=payload.status
    log_activity(db, opp.id, "status_changed", f"Status changed from {old} to {payload.status}", actor_name="Sales")
    db.commit(); db.refresh(opp)
    return opp

@app.patch("/api/opportunities/{opportunity_id}/notes", response_model=schemas.OpportunityOut)
def update_notes(opportunity_id:int, payload:schemas.NotesUpdate, db:Session=Depends(get_db)):
    opp=db.get(models.Opportunity, opportunity_id)
    if not opp: raise HTTPException(404,"Opportunity not found")
    opp.notes=payload.notes
    log_activity(db, opp.id, "notes_updated", "Updated notes", actor_name="Sales")
    db.commit(); db.refresh(opp)
    return opp

@app.get("/api/opportunities/{opportunity_id}/evidence", response_model=list[schemas.EvidenceOut])
def evidence(opportunity_id:int, db:Session=Depends(get_db)):
    return db.query(models.SourceEvidence).filter_by(opportunity_id=opportunity_id).order_by(models.SourceEvidence.created_at.desc()).all()

@app.post("/api/opportunities/{opportunity_id}/enrich", response_model=list[schemas.AccountOut])
def enrich(opportunity_id:int, db:Session=Depends(get_db)):
    opp=db.query(models.Opportunity).options(joinedload(models.Opportunity.enriched_accounts)).filter_by(id=opportunity_id).first()
    if not opp: raise HTTPException(404,"Opportunity not found")
    enrich_opportunity(db,opp); db.commit()
    return db.query(models.EnrichedAccount).options(joinedload(models.EnrichedAccount.contacts)).filter_by(opportunity_id=opportunity_id).all()

@app.get("/api/opportunities/{opportunity_id}/enrichment", response_model=list[schemas.AccountOut])
def get_enrichment(opportunity_id:int, db:Session=Depends(get_db)):
    return db.query(models.EnrichedAccount).options(joinedload(models.EnrichedAccount.contacts)).filter_by(opportunity_id=opportunity_id).all()

@app.get("/api/enriched-accounts", response_model=list[schemas.AccountOut])
def get_accounts(db:Session=Depends(get_db)):
    return db.query(models.EnrichedAccount).options(joinedload(models.EnrichedAccount.contacts)).limit(200).all()

@app.post("/api/opportunities/{opportunity_id}/research-tasks", response_model=schemas.ResearchTaskOut)
def create_research_task(opportunity_id:int, payload:schemas.ResearchTaskCreate, db:Session=Depends(get_db)):
    opp=db.get(models.Opportunity, opportunity_id)
    if not opp: raise HTTPException(404,"Opportunity not found")
    try: task=run_research_task(db, opp, payload.task_type)
    except ValueError as e: raise HTTPException(400,str(e))
    db.commit(); db.refresh(task)
    return task

@app.get("/api/opportunities/{opportunity_id}/research-tasks", response_model=list[schemas.ResearchTaskOut])
def get_research_tasks(opportunity_id:int, db:Session=Depends(get_db)):
    return db.query(models.ResearchTask).filter_by(opportunity_id=opportunity_id).order_by(models.ResearchTask.created_at.desc()).all()

@app.get("/api/opportunities/{opportunity_id}/activity", response_model=list[schemas.ActivityOut])
def get_activity(opportunity_id:int, db:Session=Depends(get_db)):
    return db.query(models.OpportunityActivity).filter_by(opportunity_id=opportunity_id).order_by(models.OpportunityActivity.created_at.desc()).all()

@app.get("/api/scoring-config", response_model=schemas.ScoringConfigOut)
def get_scoring_config(db:Session=Depends(get_db)): return active_config(db)

@app.put("/api/scoring-config", response_model=schemas.ScoringConfigOut)
def put_scoring_config(payload:schemas.ScoringConfigIn, db:Session=Depends(get_db)):
    cfg=active_config(db)
    for k,v in payload.model_dump().items(): setattr(cfg,k,v)
    db.commit(); db.refresh(cfg)
    return cfg

@app.post("/api/opportunities/rescore")
def rescore(db:Session=Depends(get_db)):
    cfg=active_config(db); count=0
    for opp in db.query(models.Opportunity).all():
        old=opp.score; score_opportunity(opp,cfg); count+=1
        if old != opp.score: log_activity(db, opp.id, "score_changed", f"Score changed from {old} to {opp.score}")
    db.commit(); return {"rescored":count}

@app.get("/api/daily-triggers", response_model=schemas.DailyTriggerResponse)
def daily_triggers(db: Session = Depends(get_db), limit: int|None=None, matter_type: str|None=None, trigger_category: str|None=None, min_source_quality: float|None=None, min_score: float|None=None, status: str|None=None, date_from: str|None=None, date_to: str|None=None, page:int=1, page_size:int|None=None):
    cfg = active_config(db)
    page_size = max(1, min(page_size or limit or cfg.max_daily_triggers or 50, cfg.max_daily_triggers or 50, 50))
    q = db.query(models.DiscoveredSignal).options(joinedload(models.DiscoveredSignal.scrape_attempts)).filter(
        models.DiscoveredSignal.gate_passed == True,
        models.DiscoveredSignal.freshness_status == "fresh",
        models.DiscoveredSignal.status != "rejected",
        models.DiscoveredSignal.duplicate_of_opportunity_id.is_(None),
    )
    if matter_type: q = q.filter(models.DiscoveredSignal.matter_type.ilike(f"%{matter_type}%"))
    if trigger_category: q = q.filter(models.DiscoveredSignal.trigger_category.ilike(f"%{trigger_category}%"))
    if min_source_quality is not None: q = q.filter(models.DiscoveredSignal.source_quality_score >= min_source_quality)
    if min_score is not None: q = q.filter(models.DiscoveredSignal.final_trigger_score >= min_score)
    if status: q = q.filter(models.DiscoveredSignal.status == status)
    if date_from: q = q.filter(models.DiscoveredSignal.published_at >= date_from)
    if date_to: q = q.filter(models.DiscoveredSignal.published_at <= date_to)
    candidates = q.order_by(
        models.DiscoveredSignal.source_tier.asc(),
        models.DiscoveredSignal.final_trigger_score.desc(),
        models.DiscoveredSignal.signal_age_days.asc().nullslast(),
        models.DiscoveredSignal.created_at.desc(),
    ).limit(200).all()
    domain_counts, category_counts, party_counts, items = {}, {}, {}, []
    tier_weight = {"tier_1_court_docket": 0, "tier_1_litigation_alert": 1, "tier_2_legal_news": 2, "tier_2_law_firm": 2, "tier_3_regulator": 3, "tier_3_business_news": 4, "low_quality": 5}
    candidates.sort(key=lambda s: (tier_weight.get(s.source_tier or "", 6), -(s.final_trigger_score or 0), s.signal_age_days if s.signal_age_days is not None else 9999))
    for s in candidates:
        domain = s.source_domain or "unknown"
        category = s.trigger_category or s.trigger_type or "unknown"
        party_key = "|".join(sorted((s.parties or [])[:2])) or s.title[:80]
        if domain_counts.get(domain, 0) >= (cfg.max_per_source_domain or 4):
            continue
        if category_counts.get(category, 0) >= (cfg.max_per_trigger_category or 5):
            continue
        if party_counts.get(party_key, 0) >= (cfg.max_per_same_party or 2):
            continue
        items.append(s)
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1
        party_counts[party_key] = party_counts.get(party_key, 0) + 1
        if len(items) >= page_size:
            break
    total = len(candidates)
    items = items[(page-1)*page_size:page*page_size]
    return {"items": items, "total": total, "page": page, "page_size": page_size}

@app.get("/api/quality-summary", response_model=schemas.QualitySummaryOut)
def quality_summary(db: Session = Depends(get_db)):
    last_run = db.query(models.WebDiscoveryRun).order_by(models.WebDiscoveryRun.created_at.desc()).first()
    rows = db.query(models.DiscoveredSignal).all()
    failure_counts = {}
    domain_counts = {}
    bad_domains, good_domains, good_categories, review_reasons = {}, {}, {}, {}
    reviewed = useful = 0
    for s in rows:
        domain = s.source_domain or "unknown"
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        reasons = s.gate_failure_reasons or ([] if s.gate_passed else [s.gate_reason or "failed_gate"])
        for reason in reasons:
            if reason:
                failure_counts[reason] = failure_counts.get(reason, 0) + 1
        if s.sales_review_status:
            reviewed += 1
            if s.sales_review_status == "useful":
                useful += 1
                good_domains[domain] = good_domains.get(domain, 0) + 1
                category = s.trigger_category or s.trigger_type or "unknown"
                good_categories[category] = good_categories.get(category, 0) + 1
            if s.sales_review_status == "not_useful":
                bad_domains[domain] = bad_domains.get(domain, 0) + 1
            if s.sales_review_reason:
                review_reasons[s.sales_review_reason] = review_reasons.get(s.sales_review_reason, 0) + 1
    return {
        "last_run_status": last_run.status if last_run else None,
        "total_raw_signals": len(rows),
        "passed_gate": sum(1 for s in rows if s.gate_passed),
        "failed_gate": sum(1 for s in rows if not s.gate_passed),
        "converted": sum(1 for s in rows if s.status == "converted"),
        "top_failure_reasons": [{"reason": k, "count": v} for k, v in sorted(failure_counts.items(), key=lambda x: x[1], reverse=True)[:5]],
        "top_source_domains": [{"domain": k, "count": v} for k, v in sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)[:5]],
        "useful_rate": round((useful / reviewed) * 100, 1) if reviewed else 0,
        "top_bad_source_domains": [{"domain": k, "count": v} for k, v in sorted(bad_domains.items(), key=lambda x: x[1], reverse=True)[:5]],
        "top_good_source_domains": [{"domain": k, "count": v} for k, v in sorted(good_domains.items(), key=lambda x: x[1], reverse=True)[:5]],
        "best_trigger_categories": [{"category": k, "count": v} for k, v in sorted(good_categories.items(), key=lambda x: x[1], reverse=True)[:5]],
        "common_rejection_reasons": [{"reason": k, "count": v} for k, v in sorted(review_reasons.items(), key=lambda x: x[1], reverse=True)[:5]],
    }

@app.get("/api/llm-status", response_model=schemas.LLMStatusOut)
def llm_status(check: bool = False):
    if check:
        return check_gemini()
    return {
        "configured": bool(settings.gemini_api_key),
        "ok": bool(settings.gemini_api_key),
        "provider": "gemini",
        "model": settings.gemini_model,
        "message": "GEMINI_API_KEY is configured." if settings.gemini_api_key else "GEMINI_API_KEY is not configured.",
    }

@app.get("/api/campaigns", response_model=list[schemas.CampaignOut])
def list_campaigns(db:Session=Depends(get_db)):
    out=[]
    for c in db.query(models.Campaign).all():
        scores=[co.opportunity.score for co in c.opportunities if co.opportunity]
        d={**c.__dict__, "opportunity_count":len(scores), "average_score":round(sum(scores)/len(scores),1) if scores else 0}
        out.append(d)
    return out

@app.post("/api/campaigns", response_model=schemas.CampaignOut)
def create_campaign(payload:schemas.CampaignCreate, db:Session=Depends(get_db)):
    c=models.Campaign(**payload.model_dump()); db.add(c); db.commit(); db.refresh(c)
    return {**c.__dict__, "opportunity_count":0, "average_score":0}

@app.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id:int, db:Session=Depends(get_db)):
    c=db.get(models.Campaign,campaign_id)
    if not c: raise HTTPException(404,"Campaign not found")
    rows=db.query(models.CampaignOpportunity).filter_by(campaign_id=campaign_id).all()
    return {"campaign": c, "opportunities": [r.opportunity for r in rows]}

@app.patch("/api/campaigns/{campaign_id}", response_model=schemas.CampaignOut)
def update_campaign(campaign_id:int, payload:schemas.CampaignCreate, db:Session=Depends(get_db)):
    c=db.get(models.Campaign,campaign_id)
    if not c: raise HTTPException(404,"Campaign not found")
    for k,v in payload.model_dump().items(): setattr(c,k,v)
    db.commit(); db.refresh(c)
    return {**c.__dict__, "opportunity_count":len(c.opportunities), "average_score":0}

@app.post("/api/campaigns/{campaign_id}/opportunities/{opportunity_id}")
def add_to_campaign(campaign_id:int, opportunity_id:int, db:Session=Depends(get_db)):
    if not db.get(models.Campaign,campaign_id): raise HTTPException(404,"Campaign not found")
    opp=db.get(models.Opportunity,opportunity_id)
    if not opp: raise HTTPException(404,"Opportunity not found")
    if not db.query(models.CampaignOpportunity).filter_by(campaign_id=campaign_id,opportunity_id=opportunity_id).first():
        db.add(models.CampaignOpportunity(campaign_id=campaign_id, opportunity_id=opportunity_id)); log_activity(db, opportunity_id, "added_to_campaign", f"Added to campaign {campaign_id}", actor_name="Sales")
    db.commit(); return {"ok":True}

@app.delete("/api/campaigns/{campaign_id}/opportunities/{opportunity_id}")
def remove_from_campaign(campaign_id:int, opportunity_id:int, db:Session=Depends(get_db)):
    row=db.query(models.CampaignOpportunity).filter_by(campaign_id=campaign_id,opportunity_id=opportunity_id).first()
    if row: db.delete(row); log_activity(db, opportunity_id, "removed_from_campaign", f"Removed from campaign {campaign_id}", actor_name="Sales")
    db.commit(); return {"ok":True}

@app.get("/api/saved-views", response_model=list[schemas.SavedViewOut])
def list_views(db:Session=Depends(get_db)): return db.query(models.SavedView).order_by(models.SavedView.is_default.desc(), models.SavedView.name.asc()).all()

@app.get("/api/sources")
def list_sources():
    return source_registry()

@app.post("/api/saved-views", response_model=schemas.SavedViewOut)
def create_view(payload:schemas.SavedViewCreate, db:Session=Depends(get_db)):
    v=models.SavedView(**payload.model_dump()); db.add(v); db.commit(); db.refresh(v); return v

@app.patch("/api/saved-views/{view_id}", response_model=schemas.SavedViewOut)
def update_view(view_id:int, payload:schemas.SavedViewCreate, db:Session=Depends(get_db)):
    v=db.get(models.SavedView,view_id)
    if not v: raise HTTPException(404,"View not found")
    for k,val in payload.model_dump().items(): setattr(v,k,val)
    db.commit(); db.refresh(v); return v

@app.delete("/api/saved-views/{view_id}")
def delete_view(view_id:int, db:Session=Depends(get_db)):
    v=db.get(models.SavedView,view_id)
    if not v: raise HTTPException(404,"View not found")
    if v.is_default: raise HTTPException(400,"Cannot delete default view")
    db.delete(v); db.commit(); return {"ok":True}

@app.get("/api/opportunities/export.csv")
def export(db:Session=Depends(get_db)):
    return Response(content=export_csv(db), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=decoverAI-opportunities.csv"})

@app.post("/api/opportunities/import.csv")
async def import_file(file: UploadFile=File(...), db:Session=Depends(get_db)):
    content=await file.read()
    return import_csv(db, content)

@app.post("/api/ingest/find")
def find(db:Session=Depends(get_db)):
    return find_signals(db)

@app.post("/api/ingest/courtlistener")
def ingest_from_courtlistener(query: str = "antitrust OR trade secret OR data breach OR securities class action", page_size: int = 10, db:Session=Depends(get_db)):
    try:
        return ingest_courtlistener(db, query=query, page_size=page_size)
    except Exception as e:
        raise HTTPException(502, f"CourtListener ingestion failed: {e}")

def _run_discovery_background(run_id: int, payload: dict):
    db = SessionLocal()
    try:
        run_discovery(db, existing_run_id=run_id, **payload)
    finally:
        db.close()

@app.post("/api/web-discovery/runs", response_model=schemas.WebDiscoveryRunOut)
def create_web_discovery_run(payload: schemas.WebDiscoveryRunCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    payload.trigger_type = payload.trigger_type or "all"
    cfg = active_config(db)
    queries = build_discovery_queries(payload.trigger_type, "US", "", enabled_source_packs(cfg.source_packs))
    run = models.WebDiscoveryRun(
        query=" | ".join(queries),
        trigger_type=payload.trigger_type,
        geography="US",
        industry="",
        time_range=payload.time_range,
        status="pending",
    )
    db.add(run); db.commit(); db.refresh(run)
    background_payload = payload.model_dump()
    background_tasks.add_task(_run_discovery_background, run.id, background_payload)
    return run

@app.get("/api/web-discovery/runs", response_model=list[schemas.WebDiscoveryRunOut])
def list_web_discovery_runs(db: Session = Depends(get_db)):
    return db.query(models.WebDiscoveryRun).order_by(models.WebDiscoveryRun.created_at.desc()).limit(100).all()

@app.get("/api/web-discovery/runs/{run_id}", response_model=schemas.WebDiscoveryRunOut)
def get_web_discovery_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(models.WebDiscoveryRun, run_id)
    if not run:
        raise HTTPException(404, "Web discovery run not found")
    return run

@app.get("/api/web-discovery/runs/{run_id}/signals", response_model=list[schemas.DiscoveredSignalOut])
def list_discovered_signals(run_id: int, tab: str = "all", page: int = 1, page_size: int = 100, db: Session = Depends(get_db)):
    run = db.get(models.WebDiscoveryRun, run_id)
    if not run:
        raise HTTPException(404, "Web discovery run not found")
    q = (
        db.query(models.DiscoveredSignal)
        .options(joinedload(models.DiscoveredSignal.scrape_attempts))
        .filter_by(discovery_run_id=run_id)
        .filter(models.DiscoveredSignal.freshness_status == "fresh")
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
    return q.order_by(models.DiscoveredSignal.final_trigger_score.desc(), models.DiscoveredSignal.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()

@app.get("/api/discovered-signals/{signal_id}", response_model=schemas.DiscoveredSignalDetailOut)
def get_discovered_signal(signal_id: int, db: Session = Depends(get_db)):
    signal = db.query(models.DiscoveredSignal).options(joinedload(models.DiscoveredSignal.scrape_attempts)).filter_by(id=signal_id).first()
    if not signal:
        raise HTTPException(404, "Discovered signal not found")
    return signal

@app.patch("/api/discovered-signals/{signal_id}/status", response_model=schemas.DiscoveredSignalOut)
def update_discovered_signal_status(signal_id: int, payload: schemas.DiscoveredSignalStatusUpdate, db: Session = Depends(get_db)):
    signal = db.query(models.DiscoveredSignal).options(joinedload(models.DiscoveredSignal.scrape_attempts)).filter_by(id=signal_id).first()
    if not signal:
        raise HTTPException(404, "Discovered signal not found")
    signal.status = payload.status
    if payload.status == "rejected":
        signal.rejection_reason = payload.rejection_reason or "Rejected by sales review."
    apply_quality_to_signal(signal, db)
    db.commit(); db.refresh(signal)
    return signal

@app.patch("/api/discovered-signals/{signal_id}/sales-review", response_model=schemas.DiscoveredSignalOut)
def update_discovered_signal_sales_review(signal_id: int, payload: schemas.SalesReviewUpdate, db: Session = Depends(get_db)):
    signal = db.query(models.DiscoveredSignal).options(joinedload(models.DiscoveredSignal.scrape_attempts)).filter_by(id=signal_id).first()
    if not signal:
        raise HTTPException(404, "Discovered signal not found")
    signal.sales_review_status = payload.review_status
    signal.sales_review_reason = payload.reason
    signal.sales_review_notes = payload.notes
    db.commit(); db.refresh(signal)
    return signal

@app.post("/api/discovered-signals/{signal_id}/convert", response_model=schemas.OpportunityOut)
def convert_discovered_signal(signal_id: int, db: Session = Depends(get_db)):
    signal = db.query(models.DiscoveredSignal).options(joinedload(models.DiscoveredSignal.discovery_run)).filter_by(id=signal_id).first()
    if not signal:
        raise HTTPException(404, "Discovered signal not found")
    if signal.status == "rejected":
        raise HTTPException(400, "Rejected signals cannot be converted")
    try:
        opp = convert_signal_to_opportunity(db, signal)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    db.commit()
    return db.query(models.Opportunity).options(joinedload(models.Opportunity.evidence)).filter_by(id=opp.id).first()
