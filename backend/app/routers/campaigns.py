from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..services import log_activity

router = APIRouter()


@router.get("/api/campaigns", response_model=list[schemas.CampaignOut])
def list_campaigns(db: Session = Depends(get_db)):
    out = []
    for campaign in db.query(models.Campaign).all():
        scores = [
            campaign_opportunity.opportunity.score
            for campaign_opportunity in campaign.opportunities
            if campaign_opportunity.opportunity
        ]
        data = {
            **campaign.__dict__,
            "opportunity_count": len(scores),
            "average_score": round(sum(scores) / len(scores), 1) if scores else 0,
        }
        out.append(data)
    return out


@router.post("/api/campaigns", response_model=schemas.CampaignOut)
def create_campaign(payload: schemas.CampaignCreate, db: Session = Depends(get_db)):
    campaign = models.Campaign(**payload.model_dump())
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return {**campaign.__dict__, "opportunity_count": 0, "average_score": 0}


@router.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.get(models.Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    rows = db.query(models.CampaignOpportunity).filter_by(campaign_id=campaign_id).all()
    return {"campaign": campaign, "opportunities": [row.opportunity for row in rows]}


@router.patch("/api/campaigns/{campaign_id}", response_model=schemas.CampaignOut)
def update_campaign(
    campaign_id: int,
    payload: schemas.CampaignCreate,
    db: Session = Depends(get_db),
):
    campaign = db.get(models.Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    for key, value in payload.model_dump().items():
        setattr(campaign, key, value)
    db.commit()
    db.refresh(campaign)
    return {
        **campaign.__dict__,
        "opportunity_count": len(campaign.opportunities),
        "average_score": 0,
    }


@router.post("/api/campaigns/{campaign_id}/opportunities/{opportunity_id}")
def add_to_campaign(
    campaign_id: int,
    opportunity_id: int,
    db: Session = Depends(get_db),
):
    if not db.get(models.Campaign, campaign_id):
        raise HTTPException(404, "Campaign not found")
    opp = db.get(models.Opportunity, opportunity_id)
    if not opp:
        raise HTTPException(404, "Opportunity not found")
    existing = (
        db.query(models.CampaignOpportunity)
        .filter_by(campaign_id=campaign_id, opportunity_id=opportunity_id)
        .first()
    )
    if not existing:
        db.add(
            models.CampaignOpportunity(
                campaign_id=campaign_id,
                opportunity_id=opportunity_id,
            )
        )
        log_activity(
            db,
            opportunity_id,
            "added_to_campaign",
            f"Added to campaign {campaign_id}",
            actor_name="Sales",
        )
    db.commit()
    return {"ok": True}


@router.delete("/api/campaigns/{campaign_id}/opportunities/{opportunity_id}")
def remove_from_campaign(
    campaign_id: int,
    opportunity_id: int,
    db: Session = Depends(get_db),
):
    row = (
        db.query(models.CampaignOpportunity)
        .filter_by(campaign_id=campaign_id, opportunity_id=opportunity_id)
        .first()
    )
    if row:
        db.delete(row)
        log_activity(
            db,
            opportunity_id,
            "removed_from_campaign",
            f"Removed from campaign {campaign_id}",
            actor_name="Sales",
        )
    db.commit()
    return {"ok": True}
