from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..db import get_db
from ..services import active_config, source_registry
from ..services.web_discovery.gemini_judge import check_gemini
from ..services.web_discovery.quality import safe_score
from ..services.web_discovery.source_packs import default_source_packs

router = APIRouter()


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


@router.get("/api/settings", response_model=schemas.SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return settings_from_config(active_config(db))


@router.put("/api/settings", response_model=schemas.SettingsOut)
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
    db.commit()
    db.refresh(cfg)
    return settings_from_config(cfg)


@router.get("/api/scoring-config", response_model=schemas.ScoringConfigOut)
def get_scoring_config(db: Session = Depends(get_db)):
    return active_config(db)


@router.put("/api/scoring-config", response_model=schemas.ScoringConfigOut)
def put_scoring_config(payload: schemas.ScoringConfigIn, db: Session = Depends(get_db)):
    cfg = active_config(db)
    for key, value in payload.model_dump().items():
        setattr(cfg, key, value)
    db.commit()
    db.refresh(cfg)
    return cfg


@router.get("/api/llm-status", response_model=schemas.LLMStatusOut)
def llm_status(check: bool = False):
    if check:
        return check_gemini()
    return {
        "configured": bool(settings.gemini_api_key),
        "ok": bool(settings.gemini_api_key),
        "provider": "gemini",
        "model": settings.gemini_model,
        "message": "GEMINI_API_KEY is configured."
        if settings.gemini_api_key
        else "GEMINI_API_KEY is not configured.",
    }


@router.get("/api/sources")
def list_sources():
    return source_registry()


@router.get("/api/saved-views", response_model=list[schemas.SavedViewOut])
def list_views(db: Session = Depends(get_db)):
    return (
        db.query(models.SavedView)
        .order_by(models.SavedView.is_default.desc(), models.SavedView.name.asc())
        .all()
    )


@router.post("/api/saved-views", response_model=schemas.SavedViewOut)
def create_view(payload: schemas.SavedViewCreate, db: Session = Depends(get_db)):
    view = models.SavedView(**payload.model_dump())
    db.add(view)
    db.commit()
    db.refresh(view)
    return view


@router.patch("/api/saved-views/{view_id}", response_model=schemas.SavedViewOut)
def update_view(
    view_id: int,
    payload: schemas.SavedViewCreate,
    db: Session = Depends(get_db),
):
    view = db.get(models.SavedView, view_id)
    if not view:
        raise HTTPException(404, "View not found")
    for key, value in payload.model_dump().items():
        setattr(view, key, value)
    db.commit()
    db.refresh(view)
    return view


@router.delete("/api/saved-views/{view_id}")
def delete_view(view_id: int, db: Session = Depends(get_db)):
    view = db.get(models.SavedView, view_id)
    if not view:
        raise HTTPException(404, "View not found")
    if view.is_default:
        raise HTTPException(400, "Cannot delete default view")
    db.delete(view)
    db.commit()
    return {"ok": True}


@router.get("/api/quality-summary", response_model=schemas.QualitySummaryOut)
def quality_summary(db: Session = Depends(get_db)):
    last_run = db.query(models.WebDiscoveryRun).order_by(models.WebDiscoveryRun.created_at.desc()).first()
    rows = db.query(models.DiscoveredSignal).all()
    failure_counts = {}
    domain_counts = {}
    bad_domains = {}
    good_domains = {}
    good_categories = {}
    review_reasons = {}
    reviewed = 0
    useful = 0
    for signal in rows:
        domain = signal.source_domain or "unknown"
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        reasons = signal.gate_failure_reasons or (
            [] if signal.gate_passed else [signal.gate_reason or "failed_gate"]
        )
        for reason in reasons:
            if reason:
                failure_counts[reason] = failure_counts.get(reason, 0) + 1
        if signal.sales_review_status:
            reviewed += 1
            if signal.sales_review_status == "useful":
                useful += 1
                good_domains[domain] = good_domains.get(domain, 0) + 1
                category = signal.trigger_category or signal.trigger_type or "unknown"
                good_categories[category] = good_categories.get(category, 0) + 1
            if signal.sales_review_status == "not_useful":
                bad_domains[domain] = bad_domains.get(domain, 0) + 1
            if signal.sales_review_reason:
                review_reasons[signal.sales_review_reason] = (
                    review_reasons.get(signal.sales_review_reason, 0) + 1
                )
    return {
        "last_run_status": last_run.status if last_run else None,
        "total_raw_signals": len(rows),
        "passed_gate": sum(1 for signal in rows if signal.gate_passed),
        "failed_gate": sum(1 for signal in rows if not signal.gate_passed),
        "converted": sum(1 for signal in rows if signal.status == "converted"),
        "top_failure_reasons": [
            {"reason": key, "count": value}
            for key, value in sorted(
                failure_counts.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:5]
        ],
        "top_source_domains": [
            {"domain": key, "count": value}
            for key, value in sorted(
                domain_counts.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:5]
        ],
        "useful_rate": round((useful / reviewed) * 100, 1) if reviewed else 0,
        "top_bad_source_domains": [
            {"domain": key, "count": value}
            for key, value in sorted(
                bad_domains.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:5]
        ],
        "top_good_source_domains": [
            {"domain": key, "count": value}
            for key, value in sorted(
                good_domains.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:5]
        ],
        "best_trigger_categories": [
            {"category": key, "count": value}
            for key, value in sorted(
                good_categories.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:5]
        ],
        "common_rejection_reasons": [
            {"reason": key, "count": value}
            for key, value in sorted(
                review_reasons.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:5]
        ],
    }
