from __future__ import annotations
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from ... import models
from .. import normalize_key

def _norm(text: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in (text or "")).split())

def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()

def find_duplicate_opportunity(db: Session, signal: models.DiscoveredSignal) -> models.Opportunity | None:
    exact = (
        db.query(models.Opportunity)
        .join(models.SourceEvidence)
        .filter(models.SourceEvidence.source_url == signal.source_url)
        .first()
    )
    if exact:
        return exact
    parties = {p.lower() for p in (signal.parties or []) if p}
    title_key = normalize_key(signal.title, signal.parties or [], signal.trigger_type or "")
    for opp in db.query(models.Opportunity).all():
        opp_parties = {p.lower() for p in (opp.parties or []) if p}
        if opp.normalized_key == title_key:
            return opp
        if parties and opp_parties and parties.intersection(opp_parties) and _similar(signal.title, opp.case_name) > 0.55:
            return opp
        if _similar(signal.summary or signal.title, opp.summary or opp.case_name) > 0.82:
            return opp
    return None

def dedupe_signal(db: Session, signal: models.DiscoveredSignal) -> int | None:
    duplicate = find_duplicate_opportunity(db, signal)
    signal.duplicate_of_opportunity_id = duplicate.id if duplicate else None
    return signal.duplicate_of_opportunity_id
