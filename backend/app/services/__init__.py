from __future__ import annotations
from datetime import datetime, timezone
from html.parser import HTMLParser
import csv, io, json, re
import httpx
from urllib.parse import urljoin, urlparse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from dateutil import parser as date_parser
from .. import models
from ..config import settings
from .web_discovery.source_packs import default_source_packs

BRAND_NAME = "decoverAI"
SOURCE_REGISTRY = [
    {
        "name": "CourtListener",
        "url": "https://www.courtlistener.com/",
        "type": "court_api",
        "mode": "live_api",
        "credibility_score": 92,
        "description": "Free Law Project source for opinions, dockets, RECAP materials, and legal search. Used by the live ingestion endpoint.",
    },
    {
        "name": "Reuters Legal News",
        "url": "https://www.reuters.com/legal/",
        "type": "legal_news",
        "mode": "live_scrape",
        "credibility_score": 90,
        "description": "High-signal legal news source for litigation, enforcement, deals, and law firm coverage. Used by the hardcoded web scraper when reachable.",
    },
    {
        "name": "U.S. DOJ Antitrust Division",
        "url": "https://www.justice.gov/atr",
        "type": "agency",
        "mode": "live_scrape",
        "credibility_score": 88,
        "description": "Primary source for antitrust enforcement actions, settlements, speeches, and press releases.",
    },
    {
        "name": "SEC Litigation Releases",
        "url": "https://www.sec.gov/litigation/litreleases",
        "type": "agency",
        "mode": "live_scrape",
        "credibility_score": 88,
        "description": "Primary source for securities enforcement litigation releases and related matters.",
    },
    {
        "name": "FTC Enforcement",
        "url": "https://www.ftc.gov/legal-library/browse/cases-proceedings",
        "type": "agency",
        "mode": "live_scrape",
        "credibility_score": 86,
        "description": "Primary source for competition, consumer protection, privacy, and data security enforcement actions.",
    },
    {
        "name": "Justia Dockets",
        "url": "https://dockets.justia.com/",
        "type": "court_index",
        "mode": "live_scrape",
        "credibility_score": 78,
        "description": "Useful public docket index for matter discovery and validation when CourtListener has limited coverage.",
    },
]

SCRAPE_SOURCES = [
    {"name": "Reuters Legal News", "url": "https://www.reuters.com/legal/", "credibility_score": 90, "allowed_paths": ["/legal/"]},
    {"name": "U.S. DOJ Antitrust Division", "url": "https://www.justice.gov/atr", "credibility_score": 88, "allowed_paths": ["/opa/pr/", "/atr/case-document", "/atr/press-release"]},
    {"name": "SEC Litigation Releases", "url": "https://www.sec.gov/litigation/litreleases", "credibility_score": 88, "allowed_paths": ["/litigation/litreleases/"]},
    {"name": "FTC Enforcement", "url": "https://www.ftc.gov/legal-library/browse/cases-proceedings", "credibility_score": 86, "allowed_paths": ["/legal-library/browse/cases-proceedings/"]},
    {"name": "Justia Dockets", "url": "https://dockets.justia.com/", "credibility_score": 78, "allowed_paths": ["/docket/"]},
]

SIGNAL_KEYWORDS = [
    "antitrust", "class action", "complaint", "copyright", "data breach", "enforcement",
    "investigation", "lawsuit", "litigation", "patent", "privacy", "securities",
    "settlement", "suit", "trade secret",
]

BAD_SCRAPE_TITLES = {
    "Anticompetitive Practices",
    "Bureau of Competition",
    "Cases and Proceedings",
    "Merger Review",
    "Rulemaking",
}

BIGLAW = {"latham", "kirkland", "skadden", "wachtell", "sullivan", "cravath", "paul weiss", "gibson", "wilmer", "quinn", "cooley", "fenwick", "morrison", "white & case", "freshfields", "sidley"}
DISCOVERY_HEAVY = {"antitrust": 95, "trade secret": 92, "ip": 88, "patent": 86, "securities": 88, "class action": 86, "data breach": 90, "regulatory": 84, "m&a dispute": 78, "employment class action": 76, "product liability": 82}
HIGH_VALUE_COMPANIES = {"nvidia", "google", "alphabet", "microsoft", "openai", "apple", "meta", "amazon", "tesla", "pfizer", "jpmorgan", "goldman", "salesforce", "oracle", "adobe", "intel", "qualcomm", "samsung", "bytedance", "x corp", "twitter"}

STATUSES = ["New", "Needs More Research", "Qualified", "Contacted", "Rejected", "Won", "Lost"]
TASK_TYPES = {"summarize_case","identify_discovery_pain","find_buyer_personas","generate_law_firm_pitch","generate_company_pitch","generate_linkedin_message","generate_call_script","generate_objection_handling","qualify_opportunity"}

def now(): return datetime.now(timezone.utc)

def normalize_key(case_name: str, parties: list[str], trigger_type: str):
    base = case_name or " ".join(parties[:2]) or "unknown"
    s = re.sub(r"[^a-z0-9]+", "-", (base + "-" + trigger_type).lower()).strip("-")
    return s[:480]

def log_activity(db: Session, opportunity_id: int, activity_type: str, message: str, actor_name="System", metadata=None):
    db.add(models.OpportunityActivity(opportunity_id=opportunity_id, activity_type=activity_type, message=message, actor_name=actor_name, metadata_json=metadata or {}))

def _get_or_create_named_entities(db: Session, model, names: list[str]):
    entities = []
    seen = set()
    for name in names:
        clean = str(name).strip()
        key = clean.lower()
        if not clean or key in seen:
            continue
        seen.add(key)
        entity = db.query(model).filter(func.lower(model.name) == key).first()
        if not entity:
            entity = model(name=clean)
            db.add(entity)
            db.flush()
        entities.append(entity)
    return entities

def _get_or_create_law_firms(db: Session, names: list[str]):
    return _get_or_create_named_entities(db, models.LawFirm, names)

def _get_or_create_personas(db: Session, names: list[str]):
    return _get_or_create_named_entities(db, models.Persona, names)

def active_config(db: Session) -> models.ScoringConfig:
    cfg = db.query(models.ScoringConfig).filter_by(is_active=True).first()
    if not cfg:
        cfg = models.ScoringConfig(name="Default", is_active=True, source_packs=default_source_packs())
        db.add(cfg); db.commit(); db.refresh(cfg)
    elif not cfg.source_packs:
        cfg.source_packs = default_source_packs()
    return cfg

def score_component_case_type(case_type: str):
    ct=(case_type or '').lower()
    for k,v in DISCOVERY_HEAVY.items():
        if k in ct: return v, f"{case_type} is commonly discovery-heavy."
    return 55, "Case type is not clearly discovery-heavy yet."

def score_opportunity(opp: models.Opportunity, cfg: models.ScoringConfig):
    case_type_score, case_reason = score_component_case_type(opp.case_type)
    law_firms = list(opp.law_firms or [])
    text = " ".join([opp.case_name, opp.case_type, opp.summary] + (opp.parties or []) + law_firms).lower()
    discovery = 55
    discovery_reasons=[]
    for kw, val in [("antitrust",95),("trade secret",92),("emails",84),("source code",90),("class action",88),("regulatory",84),("data breach",92),("securities",86),("patent",84),("documents",74)]:
        if kw in text:
            discovery=max(discovery,val); discovery_reasons.append(kw)
    company = 60
    company_hits=[p for p in (opp.parties or []) if p and p.lower() in HIGH_VALUE_COMPANIES or any(h in p.lower() for h in HIGH_VALUE_COMPANIES)]
    if company_hits: company=92
    elif len(opp.parties or []) >= 2: company=72
    law = 50
    firm_hits=[]
    for f in law_firms:
        fl=f.lower()
        if any(b in fl for b in BIGLAW): firm_hits.append(f)
    if firm_hits: law=88
    elif law_firms: law=68
    urgency = 85 if opp.trigger_type and any(x in opp.trigger_type.lower() for x in ["new", "filed", "investigation", "regulatory"]) else 65
    freshness = 80
    dfit = round((discovery*0.55 + case_type_score*0.25 + law*0.20), 1)
    weights = {
        "case_type": cfg.case_type_weight,
        "discovery_burden": cfg.discovery_burden_weight,
        "company_size": cfg.company_size_weight,
        "urgency": cfg.urgency_weight,
        "law_firm_signal": cfg.law_firm_signal_weight,
        "freshness": cfg.freshness_weight,
        "decoverAI_fit": cfg.decoverAI_fit_weight,
    }
    total_w=sum(weights.values()) or 100
    final = (
        case_type_score*weights["case_type"] + discovery*weights["discovery_burden"] + company*weights["company_size"] + urgency*weights["urgency"] + law*weights["law_firm_signal"] + freshness*weights["freshness"] + dfit*weights["decoverAI_fit"]
    )/total_w
    opp.case_type_score=round(case_type_score,1); opp.discovery_burden_score=round(discovery,1); opp.company_size_score=round(company,1)
    opp.urgency_score=round(urgency,1); opp.law_firm_signal_score=round(law,1); opp.freshness_score=round(freshness,1); opp.decoverAI_fit_score=round(dfit,1); opp.score=round(min(100,max(0,final)),1)
    opp.scoring_breakdown={
        "case_type": {"score": opp.case_type_score, "weight": cfg.case_type_weight, "reason": case_reason},
        "discovery_burden": {"score": opp.discovery_burden_score, "weight": cfg.discovery_burden_weight, "reason": "Keywords/signals: " + (", ".join(discovery_reasons) if discovery_reasons else "generic matter, needs research")},
        "company_size": {"score": opp.company_size_score, "weight": cfg.company_size_weight, "reason": "Recognized enterprise party" if company_hits else "Company size inferred from party/law firm context"},
        "urgency": {"score": opp.urgency_score, "weight": cfg.urgency_weight, "reason": "Fresh litigation/regulatory trigger"},
        "law_firm_signal": {"score": opp.law_firm_signal_score, "weight": cfg.law_firm_signal_weight, "reason": "BigLaw signal: " + ", ".join(firm_hits) if firm_hits else "No strong BigLaw match yet"},
        "freshness": {"score": opp.freshness_score, "weight": cfg.freshness_weight, "reason": "Recently captured by signal engine"},
        "decoverAI_fit": {"score": opp.decoverAI_fit_score, "weight": cfg.decoverAI_fit_weight, "reason": "Estimated fit for AI-assisted review, ECA, and document intelligence"},
    }
    opp.recommended_persona = best_persona(opp)
    opp.pitch_angle = build_pitch_angle(opp)
    opp.generated_email = build_email(opp, company_side=True)
    if not opp.confidence_score:
        opp.confidence_score = 75 if len(opp.parties or []) >= 2 else 55
    if not opp.source_quality_score:
        opp.source_quality_score = max([e.credibility_score for e in (opp.evidence or [])], default=70)
    if not opp.discovery_pain_score:
        opp.discovery_pain_score = opp.discovery_burden_score
    if not opp.dcover_fit_score:
        opp.dcover_fit_score = opp.decoverAI_fit_score
    if not opp.sales_actionability_score:
        opp.sales_actionability_score = 80 if (opp.parties and opp.evidence) else 60
    opp.final_trigger_score = round(
        opp.confidence_score * 0.20
        + opp.source_quality_score * 0.20
        + opp.discovery_pain_score * 0.25
        + opp.dcover_fit_score * 0.25
        + opp.sales_actionability_score * 0.10,
        1,
    )
    opp.score = opp.final_trigger_score or opp.score


def best_persona(opp):
    if list(opp.law_firms or []): return "Litigation Partner / eDiscovery Counsel"
    if "data breach" in (opp.case_type or '').lower(): return "General Counsel / Head of Privacy Litigation"
    return "Head of Litigation / Legal Operations"

def build_pitch_angle(opp):
    return f"Position {BRAND_NAME} around fast early case assessment and AI-assisted review for a {opp.case_type} matter with likely high document volume."

def build_email(opp, company_side=True):
    party = (opp.parties or ["your team"])[0]
    return f"""Subject: Discovery support for {opp.case_name}

Hi {{first_name}},

I noticed {party} is involved in {opp.case_name}. Matters like this often create a heavy discovery burden across emails, contracts, internal records, and business communications.

decoverAI helps legal teams ingest large document sets, surface relevant evidence faster, and reduce manual review effort with AI-assisted document intelligence.

Would it be useful to share how we could support early case assessment and discovery preparation for this matter?

Best,
decoverAI Team"""

def create_or_update_opportunity(db: Session, data: dict) -> models.Opportunity:
    parties = split_list(data.get("parties") or [])
    law_firms = split_list(data.get("law_firms") or [])
    key = normalize_key(data.get("case_name",""), parties, data.get("trigger_type","New Lawsuit"))
    opp = db.query(models.Opportunity).filter_by(normalized_key=key).first()
    created=False
    if not opp:
        opp = models.Opportunity(normalized_key=key, case_name=data.get("case_name") or "Untitled Matter")
        db.add(opp); created=True
    opp.trigger_type=data.get("trigger_type") or opp.trigger_type or "New Lawsuit"
    opp.case_type=data.get("case_type") or opp.case_type or "Unknown"
    opp.matter_type=data.get("matter_type") or opp.matter_type or opp.case_type
    opp.trigger_category=data.get("trigger_category") or opp.trigger_category or opp.trigger_type
    opp.parties=parties or opp.parties or []
    opp.party_roles=data.get("party_roles") or opp.party_roles or {}
    if law_firms:
        opp.law_firm_entities = _get_or_create_law_firms(db, law_firms)
    opp.court_or_regulator=data.get("court_or_regulator") or opp.court_or_regulator or ""
    opp.jurisdiction=data.get("jurisdiction") or opp.jurisdiction or ""
    opp.summary=data.get("summary") or opp.summary or f"Potential {opp.case_type} signal involving {', '.join(opp.parties[:3])}."
    opp.factual_basis=data.get("factual_basis") or opp.factual_basis or ""
    opp.discovery_pain_summary=data.get("discovery_pain_summary") or opp.discovery_pain_summary or ""
    opp.why_now=data.get("why_now") or opp.why_now or ""
    opp.why_decoverai=data.get("why_decoverai") or opp.why_decoverai or ""
    personas = split_list(data.get("recommended_personas") or [])
    if personas:
        opp.persona_entities = _get_or_create_personas(db, personas)
    opp.sales_angle_one_liner=data.get("sales_angle_one_liner") or opp.sales_angle_one_liner or ""
    opp.email_subject=data.get("email_subject") or opp.email_subject or ""
    opp.email_body=data.get("email_body") or opp.email_body or ""
    opp.linkedin_message=data.get("linkedin_message") or opp.linkedin_message or ""
    opp.call_opener=data.get("call_opener") or opp.call_opener or ""
    opp.confidence_score=float(data.get("confidence_score") or opp.confidence_score or 0)
    opp.source_quality_score=float(data.get("source_quality_score") or data.get("credibility_score") or opp.source_quality_score or 0)
    opp.discovery_pain_score=float(data.get("discovery_pain_score") or data.get("discovery_burden_score") or opp.discovery_pain_score or 0)
    opp.dcover_fit_score=float(data.get("dcover_fit_score") or data.get("decover_fit_score") or opp.dcover_fit_score or 0)
    opp.decoverAI_fit_score=opp.dcover_fit_score or opp.decoverAI_fit_score
    opp.sales_actionability_score=float(data.get("sales_actionability_score") or opp.sales_actionability_score or 0)
    opp.final_trigger_score=float(data.get("final_trigger_score") or opp.final_trigger_score or 0)
    opp.extraction_warnings=data.get("extraction_warnings") or opp.extraction_warnings or []
    opp.missing_fields=data.get("missing_fields") or opp.missing_fields or []
    opp.is_litigation_trigger=bool(data.get("is_litigation_trigger") if data.get("is_litigation_trigger") is not None else opp.is_litigation_trigger)
    opp.trigger_relevance_reason=data.get("trigger_relevance_reason") or opp.trigger_relevance_reason or ""
    opp.gate_status=data.get("gate_status") or opp.gate_status or ""
    opp.gate_failure_reasons=data.get("gate_failure_reasons") or opp.gate_failure_reasons or []
    opp.duplicate_confidence=float(data.get("duplicate_confidence") or opp.duplicate_confidence or 0)
    if data.get("notes"): opp.notes=data.get("notes")
    score_opportunity(opp, active_config(db))
    db.flush()
    if data.get("source_url"):
        existing = db.query(models.SourceEvidence).filter_by(opportunity_id=opp.id, source_url=data["source_url"]).first()
        if not existing:
            db.add(models.SourceEvidence(opportunity_id=opp.id, source_url=data["source_url"], source_title=data.get("source_title") or opp.case_name, publisher=data.get("publisher") or "Imported", published_at=data.get("published_at"), snippet=data.get("snippet") or opp.summary, evidence_type=data.get("evidence_type") or "legal_news", credibility_score=float(data.get("credibility_score") or 70), source_tier=data.get("source_tier") or "low_quality", source_reason=data.get("source_reason") or ""))
    log_activity(db, opp.id, "opportunity_created" if created else "opportunity_updated", f"{'Created' if created else 'Updated'} opportunity {opp.case_name}")
    return opp

def split_list(v):
    if isinstance(v, list): return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in re.split(r"[;,]", str(v)) if x.strip()]

def enrich_opportunity(db: Session, opp: models.Opportunity):
    # remove old enrichment for deterministic re-run
    for acc in list(opp.enriched_accounts): db.delete(acc)
    db.flush()
    entities=[]
    for p in opp.parties or []: entities.append((p, "company"))
    for f in list(opp.law_firms or []): entities.append((f, "law_firm"))
    for name, typ in entities:
        acc=models.EnrichedAccount(opportunity_id=opp.id, entity_name=name, entity_type=typ, website=guess_website(name), industry=infer_industry(name, opp), company_size_band=infer_size(name, typ), geography="US / Global" if typ=="company" else "US / International", description=f"{name} is involved in {opp.case_name} as a {typ.replace('_',' ')} signal.", likely_data_sources=likely_sources(opp, typ), legal_team_signal=legal_signal(opp, typ), confidence_score=78 if typ=="company" else 72)
        db.add(acc); db.flush()
        for c in personas_for(typ, opp):
            db.add(models.SuggestedContact(opportunity_id=opp.id, account_id=acc.id, persona=c[0], title_keywords=c[1], why_relevant=c[2], outreach_priority=c[3], confidence_score=c[4]))
    opp.enrichment_status="enriched"
    log_activity(db, opp.id, "enrichment_run", "Ran account and persona enrichment")

def guess_website(name):
    clean=re.sub(r"[^a-z0-9]", "", name.lower().replace("inc","").replace("llp","").replace("llc","").replace("corp", ""))
    return f"https://www.{clean}.com" if clean else ""

def infer_industry(name, opp):
    n=name.lower(); t=(opp.case_type or '').lower()
    if any(x in n for x in ["law", "llp", "latham", "kirkland", "skadden"]): return "Legal Services"
    if any(x in n for x in ["nvidia", "google", "microsoft", "openai", "apple", "meta"]): return "Technology"
    if "securities" in t: return "Financial / Public Company"
    if "data breach" in t: return "Data-Intensive Enterprise"
    return "Enterprise"

def infer_size(name, typ):
    if typ=="law_firm": return "Large law firm" if any(b in name.lower() for b in BIGLAW) else "Law firm"
    return "Enterprise" if any(h in name.lower() for h in HIGH_VALUE_COMPANIES) else "Unknown / mid-market to enterprise"

def likely_sources(opp, typ):
    base=["Email", "PDFs", "Contracts", "Internal communications"]
    ct=(opp.case_type or '').lower()
    if "trade" in ct or "ip" in ct or "patent" in ct: base += ["Source code", "Engineering documents", "Design docs"]
    if "data breach" in ct: base += ["Security logs", "Incident reports", "Customer notices"]
    if typ=="law_firm": base += ["Client productions", "Privilege review sets"]
    return base

def legal_signal(opp, typ):
    if typ=="law_firm": return "Representing counsel may need scalable review workflows, privilege review support, and early case assessment."
    return "In-house legal team may need to control discovery cost, understand facts quickly, and coordinate with outside counsel."

def personas_for(typ, opp):
    if typ=="law_firm":
        return [
            ("Litigation Partner", ["Litigation Partner", "Trial Partner", "Disputes Partner"], "Owns matter strategy and client outcomes.", 1, 78),
            ("eDiscovery Counsel", ["eDiscovery", "Discovery Counsel", "Litigation Support"], "Owns discovery workflows and review operations.", 1, 86),
            ("Litigation Support Manager", ["Litigation Support", "Practice Technology"], "Operational buyer for document review tooling.", 2, 82),
        ]
    return [
        ("Head of Litigation", ["Head of Litigation", "VP Litigation"], "Owns active disputes and outside counsel strategy.", 1, 84),
        ("Legal Operations", ["Legal Operations", "Legal Ops", "Legal Technology"], "Owns cost, workflows, vendors, and legal technology.", 1, 82),
        ("General Counsel", ["General Counsel", "Chief Legal Officer"], "Executive sponsor for high-risk litigation.", 2, 74),
        ("eDiscovery Manager", ["eDiscovery Manager", "Discovery Operations"], "Directly manages data collection, review, and production.", 1, 88),
    ]

def run_research_task(db: Session, opp: models.Opportunity, task_type: str) -> models.ResearchTask:
    if task_type not in TASK_TYPES: raise ValueError("Unsupported task_type")
    task=models.ResearchTask(opportunity_id=opp.id, task_type=task_type, status="running", input_payload={"opportunity_id": opp.id})
    db.add(task); db.flush()
    try:
        task.output_payload = deterministic_research(opp, task_type)
        task.status="completed"
        if task_type in {"generate_company_pitch", "generate_law_firm_pitch"}:
            opp.generated_email = task.output_payload.get("email", opp.generated_email)
        log_activity(db, opp.id, "research_task_completed", f"Completed AI research task: {task_type}", metadata={"task_id": task.id})
    except Exception as e:
        task.status="failed"; task.error_message=str(e)
        log_activity(db, opp.id, "research_task_failed", f"Failed AI research task: {task_type}", metadata={"error": str(e)})
    return task

def deterministic_research(opp, task_type):
    if task_type == "summarize_case":
        return {"title":"Case Summary", "text": opp.summary or f"{opp.case_name} is a {opp.case_type} matter involving {', '.join(opp.parties or [])}."}
    if task_type == "identify_discovery_pain":
        return {"title":"Discovery Pain", "bullets":["Large document review burden", "Need for early case assessment", "Privilege and confidentiality review", "Fast fact chronology over messy data", "Cost pressure from outside counsel/manual review"]}
    if task_type == "find_buyer_personas":
        return {"title":"Buyer Personas", "personas":["Head of Litigation", "Legal Operations", "eDiscovery Manager", "Litigation Partner", "Litigation Support Manager"]}
    if task_type == "generate_law_firm_pitch":
        return {"title":"Law Firm Pitch", "email": build_email(opp, company_side=False).replace("legal teams", "litigation teams").replace("your team", "your client")}
    if task_type == "generate_company_pitch":
        return {"title":"Company Pitch", "email": build_email(opp, company_side=True)}
    if task_type == "generate_linkedin_message":
        return {"title":"LinkedIn Message", "message": f"Hi {{first_name}}, noticed your team may be involved in {opp.case_name}. {BRAND_NAME} helps litigation teams handle high-volume discovery and early case assessment with AI-assisted document intelligence. Worth a quick conversation?"}
    if task_type == "generate_call_script":
        return {"title":"Call Script", "script": f"Open with the litigation trigger: {opp.case_name}. Ask whether discovery volume, privilege review, or early fact development is becoming a bottleneck. Position {BRAND_NAME} as a fast document intelligence layer."}
    if task_type == "generate_objection_handling":
        return {"title":"Objection Handling", "objections":[{"objection":"We already use Relativity/Everlaw.","response":"decoverAI can be positioned as a faster AI layer for early case assessment, targeted review, and extracting case intelligence, not necessarily a rip-and-replace."},{"objection":"Security is a concern.","response":"Lead with deployment controls, auditability, source-grounded outputs, and no unsupported claims in generated analysis."},{"objection":"No current budget.","response":"Anchor on immediate cost reduction in review and faster case strategy for this specific matter."}]}
    return {"title":"Qualification", "qualified": opp.score >= 75, "reason": f"Score {opp.score}/100 with discovery score {opp.discovery_burden_score}."}

def export_csv(db: Session):
    out=io.StringIO(); writer=csv.writer(out)
    writer.writerow(["id","score","status","case_name","trigger_type","case_type","parties","law_firms","discovery_burden_score","urgency_score","decoverAI_fit_score","recommended_persona","pitch_angle","generated_email","source_urls","notes","last_updated"])
    for o in db.query(models.Opportunity).options(joinedload(models.Opportunity.evidence)).order_by(models.Opportunity.score.desc()).all():
        writer.writerow([o.id,o.score,o.status,o.case_name,o.trigger_type,o.case_type,"; ".join(o.parties or []),"; ".join(list(o.law_firms or [])),o.discovery_burden_score,o.urgency_score,o.decoverAI_fit_score,o.recommended_persona,o.pitch_angle,o.generated_email,"; ".join([e.source_url for e in o.evidence]),o.notes,o.updated_at])
    return out.getvalue()

def import_csv(db: Session, content: bytes):
    text=content.decode('utf-8-sig')
    rows=list(csv.DictReader(io.StringIO(text)))
    created=[]; errors=[]
    for idx,row in enumerate(rows, start=2):
        try:
            if not row.get('case_name'): raise ValueError('case_name is required')
            opp=create_or_update_opportunity(db, row)
            created.append(opp.id)
        except Exception as e:
            errors.append({"row": idx, "error": str(e)})
    db.commit()
    return {"created_or_updated_ids": created, "errors": errors}

def local_signal_validation(data: dict):
    title = data.get("case_name") or data.get("source_title") or ""
    text = " ".join([title, data.get("summary") or "", data.get("snippet") or "", data.get("source_url") or ""]).lower()
    useful = (
        len(title.strip()) >= 25
        and any(keyword in text for keyword in SIGNAL_KEYWORDS)
        and title.strip() not in BAD_SCRAPE_TITLES
    )
    return {"useful": useful, "reason": "Local keyword/path validation" if useful else "Rejected by local source-quality checks"}

def parse_gemini_json(text: str):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)

def validate_signal_with_gemini(data: dict):
    fallback = local_signal_validation(data)
    if not settings.gemini_api_key:
        return fallback
    prompt = {
        "task": "Judge whether this scraped legal-source result is useful for decoverAI sales prospecting.",
        "useful_if": [
            "It is a specific litigation, investigation, enforcement action, docket, complaint, settlement, or legal article.",
            "It likely implies discovery, document review, evidence review, eDiscovery, legal operations, or litigation workload.",
        ],
        "reject_if": [
            "It is generic navigation, a practice-area landing page, a category page, an index page, or unrelated site chrome.",
            "It is not specific enough to identify a matter, article, enforcement action, docket, or legal trigger.",
        ],
        "candidate": {
            "title": data.get("case_name") or data.get("source_title"),
            "url": data.get("source_url"),
            "publisher": data.get("publisher"),
            "snippet": data.get("snippet"),
            "case_type": data.get("case_type"),
        },
        "response_format": {"useful": "boolean", "reason": "short string"},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": json.dumps(prompt)}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(url, headers={"x-goog-api-key": settings.gemini_api_key}, json=body)
            response.raise_for_status()
            payload = response.json()
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        result = parse_gemini_json(text)
        return {"useful": bool(result.get("useful")), "reason": str(result.get("reason") or "Gemini validation")}
    except Exception as e:
        fallback["reason"] = f"{fallback['reason']} ; Gemini validation unavailable: {e}"
        return fallback

def source_registry():
    return SOURCE_REGISTRY

def infer_case_type_from_text(text: str):
    t = text.lower()
    if "antitrust" in t or "monopoly" in t: return "Antitrust"
    if "trade secret" in t: return "Trade Secret / IP"
    if "patent" in t or "copyright" in t or "trademark" in t: return "IP"
    if "data breach" in t or "privacy" in t or "cyber" in t: return "Data Breach"
    if "securities" in t or "shareholder" in t: return "Securities"
    if "class action" in t: return "Class Action"
    return "Litigation"

def parse_case_parties(case_name: str):
    parts = re.split(r"\s+(?:v\.?|vs\.?|versus)\s+", case_name, flags=re.IGNORECASE)
    return [p.strip(" ,") for p in parts[:2] if p.strip(" ,")]

def display_case_name(case_name: str):
    cleaned = re.sub(r"^\s*in\s+re\s*:?\s*", "", case_name or "", flags=re.IGNORECASE).strip()
    return cleaned or case_name or "Untitled Matter"

def clean_parties(parties: list[str], case_name: str):
    case_key = re.sub(r"[^a-z0-9]+", "", case_name.lower())
    out = []
    for party in parties or []:
        p = str(party).strip()
        key = re.sub(r"[^a-z0-9]+", "", p.lower())
        if not p or key == case_key or p.lower() in {"service list", "all defendants", "all plaintiffs"}:
            continue
        if p not in out:
            out.append(p)
    return out[:8]

class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.current = {"href": href, "text": []}

    def handle_data(self, data):
        if self.current:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current:
            text = " ".join(" ".join(self.current["text"]).split())
            if text:
                self.links.append({"href": self.current["href"], "text": text})
            self.current = None

class PageMetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.in_h1 = False
        self.title = ""
        self.h1 = ""
        self.description = ""

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "h1" and not self.h1:
            self.in_h1 = True
        if tag == "meta":
            name = (attr.get("name") or attr.get("property") or "").lower()
            if name in {"description", "og:description"} and attr.get("content") and not self.description:
                self.description = " ".join(attr["content"].split())

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_h1:
            self.h1 += data

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "h1":
            self.in_h1 = False

def page_metadata(client: httpx.Client, source_url: str):
    try:
        response = client.get(source_url)
        response.raise_for_status()
    except Exception:
        return {}
    parser = PageMetadataParser()
    parser.feed(response.text[:200000])
    title = " ".join((parser.h1 or parser.title).split())
    title = re.sub(r"\s+\|\s+.*$", "", title).strip()
    return {"title": title, "description": parser.description}

def is_signal_link(text: str, href: str, allowed_paths: list[str]):
    path = urlparse(href).path
    if allowed_paths and not any(path.startswith(allowed) for allowed in allowed_paths):
        return False
    if text.strip() in BAD_SCRAPE_TITLES:
        return False
    if len(text.strip()) < 25 and not re.search(r"\bv\.?\b|\bvs\.?\b", text, re.IGNORECASE):
        return False
    haystack = f"{text} {href}".lower()
    if not any(keyword in haystack for keyword in SIGNAL_KEYWORDS):
        return False
    if any(skip in haystack for skip in ["javascript:", "mailto:", "#", "/video/", "/pictures/"]):
        return False
    return True

def article_source_label(source_url: str):
    host = urlparse(source_url).netloc.replace("www.", "")
    return host or source_url

def scrape_source(source: dict, limit: int):
    headers = {"User-Agent": "decoverAI-signal-workspace/2.0 (+sales research; contact: local)"}
    with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
        response = client.get(source["url"])
        response.raise_for_status()
        parser = LinkExtractor()
        parser.feed(response.text)
        rows = []
        seen = set()
        for link in parser.links:
            anchor_title = link["text"].strip()
            source_url = urljoin(source["url"], link["href"])
            if source_url in seen or not is_signal_link(anchor_title, source_url, source.get("allowed_paths", [])):
                continue
            seen.add(source_url)
            meta = page_metadata(client, source_url)
            title = (meta.get("title") or anchor_title).strip()
            snippet = meta.get("description") or title
            if not is_signal_link(title, source_url, source.get("allowed_paths", [])):
                continue
            rows.append({
                "case_name": display_case_name(title[:300]),
                "trigger_type": "Web Scrape Signal",
                "case_type": infer_case_type_from_text(" ".join([title, snippet])),
                "parties": parse_case_parties(title),
                "law_firms": [],
                "summary": f"Scraped from {source['name']}: {snippet}",
                "source_url": source_url,
                "source_title": title[:500],
                "publisher": source["name"],
                "snippet": snippet[:2000],
                "evidence_type": "scraped_legal_source",
                "credibility_score": source["credibility_score"],
            })
            if len(rows) >= limit:
                break
    return rows

def _parse_dt_safe(value: str | None):
    if not value:
        return None
    try:
        dt = date_parser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def _get_cl_date(row: dict):
    dates = []
    for key in ["dateFiled", "date_filed", "dateArgued", "dateCreated", "date_created"]:
        parsed = _parse_dt_safe(row.get(key))
        if parsed:
            dates.append(parsed)
    for doc in row.get("recap_documents") or []:
        for key in ["entry_date_filed", "dateFiled", "date_filed", "dateCreated", "date_created"]:
            parsed = _parse_dt_safe(doc.get(key))
            if parsed:
                dates.append(parsed)
    return max(dates) if dates else None

def courtlistener_url(row: dict):
    docs = row.get("recap_documents") or []
    complaint = next((doc for doc in docs if "complaint" in " ".join([doc.get("description") or "", doc.get("short_description") or ""]).lower() and doc.get("absolute_url")), None)
    available = next((doc for doc in docs if doc.get("is_available") and doc.get("absolute_url")), None)
    any_doc = next((doc for doc in docs if doc.get("absolute_url")), None)
    absolute_url = (complaint or available or any_doc or {}).get("absolute_url") or row.get("docket_absolute_url") or ""
    return "https://www.courtlistener.com" + absolute_url if absolute_url.startswith("/") else absolute_url or ""

def ingest_courtlistener(db: Session, query: str = "antitrust OR trade secret OR data breach", page_size: int = 10):
    url = "https://www.courtlistener.com/api/rest/v4/search/"
    requested = max(1, min(page_size, 25))
    params = {"q": query, "type": "r", "order_by": "score desc", "page_size": requested}
    created = []
    with httpx.Client(timeout=12, headers={"User-Agent": "decoverAI-signal-workspace/2.0"}) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    for row in payload.get("results", [])[:requested]:
        raw_case_name = row.get("caseName") or row.get("case_name") or row.get("caseNameFull") or row.get("docketNumber") or "CourtListener Matter"
        case_name = display_case_name(raw_case_name)
        snippet = re.sub(r"<[^>]+>", "", row.get("snippet") or row.get("text") or "").strip()
        source_url = courtlistener_url(row)
        if not source_url:
            continue
        text = " ".join([case_name, snippet])
        data = {
            "case_name": case_name[:300],
            "trigger_type": "CourtListener Signal",
            "case_type": infer_case_type_from_text(text),
            "parties": clean_parties(row.get("party") or parse_case_parties(raw_case_name), raw_case_name),
            "law_firms": row.get("firm") or [],
            "summary": snippet or f"CourtListener result for {raw_case_name}.",
            "source_url": source_url,
            "source_title": raw_case_name[:500],
            "publisher": "CourtListener",
            "published_at": _get_cl_date(row),
            "snippet": snippet[:2000] if snippet else "Matched CourtListener legal search result.",
            "evidence_type": "court_record",
            "credibility_score": 92,
        }
        validation = validate_signal_with_gemini(data)
        if not validation["useful"]:
            continue
        opp = create_or_update_opportunity(db, data)
        if opp.id not in created:
            created.append(opp.id)
    db.commit()
    return {"source": "CourtListener", "query": query, "created_or_updated_ids": created, "count": len(created)}

def scrape_legal_sources(db: Session, per_source: int = 5):
    created = []
    errors = []
    rejected = []
    for source in SCRAPE_SOURCES:
        try:
            for data in scrape_source(source, per_source):
                validation = validate_signal_with_gemini(data)
                if not validation["useful"]:
                    rejected.append({"source": source["name"], "title": data.get("case_name"), "reason": validation["reason"]})
                    continue
                opp = create_or_update_opportunity(db, data)
                log_activity(db, opp.id, "signal_validated", f"Validated scraped signal: {validation['reason']}", metadata={"validator": "gemini" if settings.gemini_api_key else "local"})
                if opp.id not in created:
                    created.append(opp.id)
        except Exception as e:
            errors.append({"source": source["name"], "error": str(e)})
    db.commit()
    return {"source": "Hardcoded legal web scraper", "created_or_updated_ids": created, "count": len(created), "errors": errors, "rejected": rejected}

def find_signals(db: Session):
    results = []
    try:
        results.append(ingest_courtlistener(db, page_size=10))
    except Exception as e:
        results.append({"source": "CourtListener", "error": str(e), "created_or_updated_ids": [], "count": 0})
    results.append(scrape_legal_sources(db, per_source=5))
    ids = []
    errors = []
    for result in results:
        ids.extend(result.get("created_or_updated_ids", []))
        errors.extend(result.get("errors", []))
        errors.extend(result.get("rejected", []))
        if result.get("error"):
            errors.append({"source": result.get("source", "Unknown"), "error": result["error"]})
    unique_ids = list(dict.fromkeys(ids))
    return {"created_or_updated_ids": unique_ids, "count": len(unique_ids), "sources": results, "errors": errors}

def remove_demo_opportunities(db: Session):
    demo_names = {
        "NVIDIA v. VectorCompute",
        "State AGs v. MegaSearch",
        "Customers v. FinBank",
        "Shareholders v. BioPharmaCo",
    }
    for opp in db.query(models.Opportunity).options(joinedload(models.Opportunity.evidence)).all():
        has_demo_evidence = any("Demo Seed" in (e.publisher or "") or "example.com" in (e.source_url or "") for e in opp.evidence)
        has_bad_scrape_evidence = any(e.evidence_type == "scraped_legal_source" and (e.source_title or "") in BAD_SCRAPE_TITLES for e in opp.evidence)
        if opp.case_name in demo_names or has_demo_evidence or has_bad_scrape_evidence:
            db.delete(opp)

def remove_low_quality_scraped_opportunities(db: Session):
    for opp in db.query(models.Opportunity).options(joinedload(models.Opportunity.evidence)).all():
        scraped = [e for e in opp.evidence if e.evidence_type == "scraped_legal_source"]
        if not scraped:
            continue
        data = {
            "case_name": opp.case_name,
            "case_type": opp.case_type,
            "summary": opp.summary,
            "source_url": scraped[0].source_url,
            "source_title": scraped[0].source_title,
            "publisher": scraped[0].publisher,
            "snippet": scraped[0].snippet,
        }
        if not validate_signal_with_gemini(data)["useful"]:
            db.delete(opp)

def remove_non_specific_courtlistener_links(db: Session):
    homepage_urls = {"https://www.courtlistener.com", "https://www.courtlistener.com/"}
    for opp in db.query(models.Opportunity).options(joinedload(models.Opportunity.evidence)).all():
        if any(e.publisher == "CourtListener" and (e.source_url or "").rstrip("/") in {url.rstrip("/") for url in homepage_urls} for e in opp.evidence):
            db.delete(opp)

def clean_existing_case_names(db: Session):
    cfg = active_config(db)
    for opp in db.query(models.Opportunity).options(joinedload(models.Opportunity.evidence)).all():
        cleaned = display_case_name(opp.case_name)
        if cleaned != opp.case_name:
            old_name = opp.case_name
            opp.case_name = cleaned
            opp.parties = clean_parties(opp.parties or [], old_name)
            if not opp.summary or old_name in opp.summary:
                opp.summary = (opp.summary or f"CourtListener result for {old_name}.").replace(old_name, cleaned)
            score_opportunity(opp, cfg)

def seed(db: Session):
    if not db.query(models.ScoringConfig).first(): db.add(models.ScoringConfig(name="Default", is_active=True))
    remove_demo_opportunities(db)
    remove_low_quality_scraped_opportunities(db)
    remove_non_specific_courtlistener_links(db)
    clean_existing_case_names(db)
    if settings.enable_demo_data and not db.query(models.Campaign).first():
        for name,seg in [("Antitrust Litigation","Antitrust"),("IP / Trade Secret Disputes","IP and trade secrets"),("Securities Class Actions","Securities"),("Data Breach Litigation","Data breach"),("BigLaw Represented Matters","BigLaw")]:
            db.add(models.Campaign(name=name, description=f"Outbound motion for {seg} matters", target_segment=seg, owner_name="Sales", status="active"))
    if settings.enable_demo_data and not db.query(models.SavedView).first():
        defaults=[
            ("All Signals",{}, {"field":"score","direction":"desc"}),
            ("High Score",{"min_score":80}, {"field":"score","direction":"desc"}),
            ("New This Week",{"status":"New"}, {"field":"updated_at","direction":"desc"}),
            ("BigLaw Matters",{"has_law_firms":True}, {"field":"score","direction":"desc"}),
            ("Antitrust",{"case_type":"Antitrust"}, {"field":"score","direction":"desc"}),
            ("IP / Trade Secret",{"case_type":"Trade Secret"}, {"field":"score","direction":"desc"}),
            ("Data Breach",{"case_type":"Data Breach"}, {"field":"score","direction":"desc"}),
            ("Needs Research",{"enrichment_status":"pending"}, {"field":"score","direction":"desc"}),
            ("Qualified",{"status":"Qualified"}, {"field":"score","direction":"desc"}),
        ]
        for name,filters,sort in defaults: db.add(models.SavedView(name=name, filters=filters, sort=sort, is_default=True))
    db.commit()
