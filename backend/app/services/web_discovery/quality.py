from __future__ import annotations
import math
from datetime import datetime, timezone
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from ... import models
from ...config import settings

DISCOVERY_PAIN_TERMS = {
    "document volume": 88, "documents": 76, "esi": 86, "emails": 84, "contracts": 78,
    "financial records": 82, "communications": 78, "subpoena": 90, "production deadline": 94,
    "privilege": 90, "privilege log": 94, "redaction": 90, "regulatory production": 90,
    "internal investigation": 86, "government investigation": 88, "multi-party": 84,
    "class action": 86, "antitrust": 92, "trade secret": 92, "fraud": 84,
    "healthcare fraud": 90, "data breach": 90, "construction defect": 82,
    "commercial litigation": 78, "securities": 86, "white collar": 88,
}

DCOVER_CAPABILITIES = [
    "classification", "responsiveness review", "privilege analysis", "confidentiality analysis",
    "redaction", "Bates numbering", "privilege logs", "production setup",
    "early case assessment", "chronology", "evidence analysis", "audit trails",
    "fast production", "lower review cost",
]

TIER_1_COURT = {"courtlistener.com", "recap.email", "pacer.uscourts.gov", "uscourts.gov", "dockets.justia.com"}
TIER_1_ALERT = {"law.com/radar", "docketalarm.com", "unicourt.com", "trellis.law"}
TIER_2_LEGAL_NEWS = {"reuters.com", "law.com", "bloomberglaw.com", "law360.com", "jdsupra.com", "natlawreview.com", "barandbench.com", "livelaw.in"}
TIER_3_REGULATORS = {"sec.gov", "justice.gov", "ftc.gov", "hhs.gov", "oig.hhs.gov"}
LOW_QUALITY_HINTS = ["blog", "mirror", "contentfarm", "seo", "ai-news", "scraped"]

HIGH_QUALITY_DOMAINS = {
    "courtlistener.com": 96, "justice.gov": 68, "sec.gov": 62, "ftc.gov": 66,
    "uscourts.gov": 92, "reuters.com": 88, "law.com": 84, "law360.com": 82,
    "jdsupra.com": 76, "natlawreview.com": 74, "barandbench.com": 76,
    "livelaw.in": 76, "dockets.justia.com": 78, "justia.com": 78,
}

STRONG_TRIGGER_TERMS = [
    "lawsuit", "sued", "sues", "complaint", "class action", "settlement", "charges",
    "charged", "indictment", "investigation", "probe", "subpoena", "enforcement action",
    "filed", "litigation", "false claims act", "anti-kickback", "breach notification",
]

NEGATIVE_GENERIC_TERMS = [
    "policy statement", "rulemaking", "guidance only", "guidance", "annual report",
    "opinion article", "general update", "client alert", "newsletter", "webinar",
    "speech", "remarks", "fact sheet", "framework", "proposal",
    "policy regarding denials", "policy regarding settlements", "rescinds policy",
    "investor bulletin", "enforcement manual",
]

GENERIC_FIT_PHRASES = ["legal documents", "can help with documents", "legal work", "legal teams generally"]

def safe_score(value, default=0) -> int:
    if value is None:
        value = default
    try:
        number = float(value)
    except Exception:
        number = float(default or 0)
    if math.isnan(number) or math.isinf(number):
        number = float(default or 0)
    return int(round(max(0, min(100, number))))

def bounded(value, default=0):
    return safe_score(value, default)

def _domain(url: str) -> str:
    return urlparse(url or "").netloc.lower().replace("www.", "")

def classify_source(url: str, publisher: str = "", title: str = "", text: str = "") -> dict:
    domain = _domain(url)
    haystack = " ".join([url or "", publisher or "", title or "", text or ""]).lower()
    if not domain:
        return {"source_tier": "blocked", "source_reason": "Source has no domain."}
    if any(hint in domain for hint in LOW_QUALITY_HINTS):
        return {"source_tier": "low_quality", "source_reason": "Domain looks like a generic blog, mirror, or SEO source."}
    if any(domain.endswith(d) for d in TIER_1_COURT) or "recap" in haystack:
        return {"source_tier": "tier_1_court_docket", "source_reason": "Court/docket or RECAP-style source."}
    if any(d in haystack for d in TIER_1_ALERT):
        return {"source_tier": "tier_1_litigation_alert", "source_reason": "Docket/litigation alert source."}
    if any(domain.endswith(d) for d in TIER_2_LEGAL_NEWS):
        if "law firm" in haystack or "client alert" in haystack:
            return {"source_tier": "tier_2_law_firm", "source_reason": "Law firm or legal alert discussing a matter."}
        return {"source_tier": "tier_2_legal_news", "source_reason": "Trusted legal news source."}
    if any(domain.endswith(d) for d in TIER_3_REGULATORS) or domain.endswith(".gov"):
        return {"source_tier": "tier_3_regulator", "source_reason": "Regulator/government source; actionability is evaluated separately."}
    if any(x in domain for x in ["prnewswire", "businesswire", "globenewswire"]):
        return {"source_tier": "tier_3_business_news", "source_reason": "Company press release or business wire source."}
    return {"source_tier": "low_quality", "source_reason": "Source is not in a trusted court, legal news, regulator, or law firm tier."}

def source_quality_for_tier(tier: str, actionable_regulator: bool = False) -> int:
    if tier == "tier_1_court_docket":
        return 96
    if tier == "tier_1_litigation_alert":
        return 90
    if tier in {"tier_2_legal_news", "tier_2_law_firm"}:
        return 82
    if tier in {"tier_3_regulator", "tier_3_business_news"}:
        return 72 if actionable_regulator else 58
    if tier == "blocked":
        return 0
    return 38

REGULATOR_ACTION_TERMS = ["enforcement action", "complaint", "charges", "charged", "settlement", "subpoena", "investigation", "consent order", "indictment", "lawsuit", "sued"]
REGULATOR_NON_ACTION_TERMS = ["policy", "rulemaking", "guidance", "speech", "annual report", "manual", "investor bulletin", "remarks", "rescinds policy"]

class RegulatorActionabilityClassifier:
    @staticmethod
    def classify(data: dict) -> dict:
        tier = data.get("source_tier") or classify_source(data.get("source_url") or "").get("source_tier")
        if tier != "tier_3_regulator":
            return {"actionable": True, "reason": ""}
        text = " ".join(str(data.get(k) or "") for k in ["title", "summary", "factual_basis", "raw_snippet", "scraped_text", "discovery_pain_summary"]).lower()
        parties = data.get("parties") or []
        action_hits = [term for term in REGULATOR_ACTION_TERMS if term in text]
        non_action_hits = [term for term in REGULATOR_NON_ACTION_TERMS if term in text]
        burden = any(term in text for term in ["documents", "records", "emails", "subpoena", "production", "investigation", "redaction", "privilege"])
        if len(parties) >= 1 and action_hits and burden:
            return {"actionable": True, "reason": f"Regulator source names a party and includes {', '.join(action_hits[:3])} with likely document burden."}
        reasons = []
        if not parties:
            reasons.append("no target company/person")
        if not action_hits:
            reasons.append("no complaint, charges, settlement, subpoena, or investigation")
        if not burden:
            reasons.append("no clear discovery or regulatory-response burden")
        if non_action_hits:
            reasons.append(f"policy/general content: {', '.join(non_action_hits[:3])}")
        return {"actionable": False, "reason": "; ".join(reasons) or "not sales-actionable regulator item"}

def evaluate_freshness(data: dict, max_age_days: int | None = None) -> dict:
    max_age_days = int(max_age_days or settings.max_signal_age_days or 90)
    date_value = data.get("filing_date") or data.get("signal_date") or data.get("published_at")
    source = "filing_date" if data.get("filing_date") else "published_at" if data.get("published_at") else ""
    weak = False
    if not date_value and data.get("discovered_at"):
        date_value = data.get("discovered_at")
        source = "discovered_at"
        weak = True
    if isinstance(date_value, str):
        try:
            date_value = datetime.fromisoformat(date_value.replace("Z", "+00:00"))
        except ValueError:
            date_value = None
    if date_value and date_value.tzinfo is None:
        date_value = date_value.replace(tzinfo=timezone.utc)
    if not date_value:
        return {"signal_date": None, "signal_age_days": None, "freshness_status": "unknown", "freshness_reason": "unknown_date"}
    now = datetime.now(timezone.utc)
    age = max(0, (now - date_value.astimezone(timezone.utc)).days)
    if weak:
        return {"signal_date": date_value, "signal_age_days": age, "freshness_status": "unknown", "freshness_reason": "weak_discovered_at_only"}
    if age > max_age_days:
        return {"signal_date": date_value, "signal_age_days": age, "freshness_status": "stale", "freshness_reason": "stale_signal"}
    return {"signal_date": date_value, "signal_age_days": age, "freshness_status": "fresh", "freshness_reason": f"{source or 'source_date'} within {max_age_days} days"}

def source_quality_for(url: str, publisher: str = "") -> float:
    domain = _domain(url)
    if not domain:
        return 35
    if domain == "example.com":
        return 30 if not settings.enable_demo_data else 70
    for key, score in HIGH_QUALITY_DOMAINS.items():
        if domain.endswith(key):
            return score
    if domain.endswith(".gov") or domain.endswith(".us"):
        return 58
    if any(name in (publisher or "").lower() for name in ["court", "agency", "regulator"]):
        return 78
    if any(x in domain for x in ["blog", "mirror", "contentfarm"]):
        return 42
    return 68

def classify_litigation_trigger(data: dict) -> dict:
    text = " ".join(str(data.get(k) or "") for k in [
        "title", "summary", "factual_basis", "raw_snippet", "scraped_text",
        "matter_type", "trigger_category", "discovery_pain_summary",
    ]).lower()
    strong_hits = [term for term in STRONG_TRIGGER_TERMS if term in text]
    negative_hits = [term for term in NEGATIVE_GENERIC_TERMS if term in text]
    parties = data.get("parties") or []
    court = data.get("court_or_regulator") or ""
    regulator = RegulatorActionabilityClassifier.classify(data)
    if not regulator["actionable"]:
        return {"is_litigation_trigger": False, "trigger_relevance_reason": regulator["reason"], "rejection_reason": regulator["reason"], "gate_failure_reasons": ["not_sales_actionable_regulator_item"]}
    if negative_hits and not strong_hits:
        return {"is_litigation_trigger": False, "trigger_relevance_reason": "", "rejection_reason": f"Generic source content: {', '.join(negative_hits[:3])}"}
    if not strong_hits:
        return {"is_litigation_trigger": False, "trigger_relevance_reason": "", "rejection_reason": "No lawsuit, complaint, investigation, charges, settlement, subpoena, or class action signal found."}
    if not parties and not court:
        return {"is_litigation_trigger": False, "trigger_relevance_reason": "", "rejection_reason": "No named party, court, or regulator found."}
    return {"is_litigation_trigger": True, "trigger_relevance_reason": f"Actionable trigger terms: {', '.join(strong_hits[:4])}.", "rejection_reason": ""}

def recommended_personas(signal: dict) -> list[str]:
    firms = signal.get("law_firms") or []
    matter = " ".join([signal.get("matter_type") or "", signal.get("trigger_category") or "", signal.get("summary") or ""]).lower()
    if firms:
        return ["Litigation Partner", "eDiscovery Counsel", "Litigation Support Manager"]
    if "data breach" in matter or "privacy" in matter:
        return ["General Counsel", "Head of Privacy Litigation", "eDiscovery Manager"]
    if "government" in matter or "regulatory" in matter or "investigation" in matter:
        return ["General Counsel", "Investigations Counsel", "Legal Operations"]
    return ["Head of Litigation", "Legal Operations", "eDiscovery Manager"]

def score_discovery_pain(text: str, parties: list[str] | None = None, law_firms: list[str] | None = None) -> tuple[float, list[str]]:
    lower = (text or "").lower()
    score = 50
    reasons = []
    for term, value in DISCOVERY_PAIN_TERMS.items():
        if term in lower:
            score = max(score, value)
            reasons.append(term)
    if parties and len(parties) >= 2:
        score = max(score, 72)
        reasons.append("clear opposing parties")
    if law_firms:
        score = max(score, 76)
        reasons.append("law firm involvement")
    return bounded(score, 50), list(dict.fromkeys(reasons))[:10]

def score_dcover_fit(discovery_pain_score: float, text: str) -> tuple[float, list[str]]:
    lower = (text or "").lower()
    matched = []
    score = discovery_pain_score * 0.65 + 18
    capability_map = {
        "classification": ["documents", "esi", "records", "pdf"],
        "responsiveness review": ["document review", "responsive", "production", "discovery"],
        "privilege analysis": ["privilege", "attorney-client"],
        "confidentiality analysis": ["confidential", "protective order", "trade secret"],
        "redaction": ["redaction", "privacy", "personal information", "data breach"],
        "Bates numbering": ["production", "court-ready", "discovery"],
        "privilege logs": ["privilege log", "privilege"],
        "production setup": ["production", "subpoena", "regulatory production"],
        "early case assessment": ["filed", "complaint", "investigation", "new lawsuit"],
        "chronology": ["fraud", "investigation", "communications"],
        "evidence analysis": ["evidence", "records", "emails", "communications"],
        "audit trails": ["defensible", "regulatory", "government investigation"],
    }
    for capability, terms in capability_map.items():
        if any(term in lower for term in terms):
            matched.append(capability)
    if matched:
        score = max(score, 72 + min(len(matched) * 3, 18))
    return bounded(score, 55), matched[:8]

def sales_assets(data: dict) -> dict:
    title = data.get("title") or data.get("case_name") or "this matter"
    party = (data.get("parties") or ["your team"])[0]
    matter = data.get("matter_type") or data.get("case_type") or "litigation"
    pain = data.get("discovery_pain_summary") or "likely document review, privilege, redaction, and production work"
    angle = f"Help {party} move faster on {matter} discovery: {pain}."
    email_subject = f"Discovery support for {title[:80]}"
    email_body = (
        f"Hi {{first_name}},\n\n"
        f"I saw {title}. Based on the public source, this looks like a {matter} trigger where the team may need fast, defensible discovery workflows.\n\n"
        f"DecoverAI can help with document classification, responsiveness and privilege review, redaction, privilege logs, Bates numbering, production setup, early case assessment, and audit trails.\n\n"
        f"Would it be useful to compare notes on where discovery burden may show up first?\n\n"
        f"Best,\nDecoverAI Team"
    )
    return {
        "recommended_personas": data.get("recommended_personas") or recommended_personas(data),
        "sales_angle_one_liner": data.get("sales_angle_one_liner") or angle,
        "email_subject": data.get("email_subject") or email_subject,
        "email_body": data.get("email_body") or email_body,
        "linkedin_message": data.get("linkedin_message") or f"Noticed {title}. DecoverAI helps litigation teams speed up review, privilege, redaction, production setup, and early case assessment when discovery pressure ramps up.",
        "call_opener": data.get("call_opener") or f"I’m calling because {title} may create near-term discovery work around review, privilege, redaction, and production readiness.",
    }

def sales_action_plan(data: dict) -> dict:
    party = (data.get("parties") or ["the legal team"])[0]
    personas = data.get("recommended_personas") or recommended_personas(data)
    pain = data.get("discovery_pain_summary") or "near-term review, privilege, redaction, and production work"
    title = data.get("title") or "the new matter"
    capability = "classification, responsiveness review, privilege review, redaction, production setup, and audit trails"
    lower = pain.lower()
    if "privilege" in lower:
        capability = "privilege review, privilege logs, and defensible audit trails"
    elif "redaction" in lower or "confidential" in lower:
        capability = "redaction, confidentiality review, and production controls"
    elif "production" in lower or "subpoena" in lower:
        capability = "Bates numbering, production setup, and defensible production"
    elif "investigation" in lower:
        capability = "chronology, evidence analysis, and fast document review"
    first_touch = f"I saw {title}. It looks like {party} may be facing {pain}. DecoverAI can help with {capability} before discovery pressure compounds."
    return {
        "recommended_account": party,
        "recommended_persona": personas[0] if personas else "Head of Litigation",
        "recommended_contact_titles": personas,
        "why_this_persona": "This person usually owns litigation discovery cost, speed, privilege risk, and production readiness.",
        "outreach_priority": "high" if safe_score(data.get("final_trigger_score"), 0) >= 85 else "medium",
        "first_touch_angle": first_touch,
        "second_touch_angle": f"Lead with reducing manual review and privilege risk in {title}.",
        "discovery_pain_hypothesis": pain,
        "questions_to_ask_on_call": [
            "What discovery deadlines or preservation issues are already visible?",
            "Where do you expect the largest document volume?",
            "How are privilege, redaction, and production being handled today?",
            "Which outside counsel or internal teams own review strategy?",
        ],
        "likely_objections": ["We already have review tools.", "It is too early.", "Outside counsel handles this."],
        "objection_responses": [
            "DecoverAI can complement existing review by accelerating classification, privilege, redaction, and production prep.",
            "Early case assessment is exactly where teams can avoid expensive manual triage later.",
            "Outside counsel still benefits from cleaner evidence organization, auditability, and faster review workflows.",
        ],
        "proof_points_to_use": ["classification", "responsiveness review", "privilege logs", "redaction", "Bates numbering", "audit trails"],
        "next_best_action": "Find litigation/eDiscovery owner at the named company or involved law firm and send the first-touch angle with the source link.",
        "suggested_first_email": data.get("email_body") or first_touch,
        "suggested_linkedin_message": data.get("linkedin_message") or first_touch[:280],
        "call_opener": data.get("call_opener") or f"I am calling because {title} looks like it may create urgent discovery work.",
    }

def score_signal_payload(data: dict) -> dict:
    text = " ".join(str(data.get(k) or "") for k in ["title", "matter_type", "trigger_category", "summary", "factual_basis", "discovery_pain_summary", "why_now", "why_decoverai"])
    parties = data.get("parties") or []
    law_firms = data.get("law_firms") or []
    source_info = classify_source(data.get("source_url") or "", data.get("publisher") or "", data.get("title") or "", text)
    data = {**data, **source_info}
    regulator = RegulatorActionabilityClassifier.classify(data)
    source_quality = safe_score(data.get("source_quality_score"), source_quality_for_tier(source_info["source_tier"], regulator["actionable"]))
    pain, pain_reasons = score_discovery_pain(text, parties, law_firms)
    dcover_fit, fit_reasons = score_dcover_fit(pain, text)
    confidence = safe_score(data.get("confidence_score"), 72 if len(parties) >= 2 else 58)
    actionability = 52
    if len(parties) >= 2:
        actionability += 18
    if data.get("source_url"):
        actionability += 10
    if data.get("sales_angle_one_liner") or data.get("summary"):
        actionability += 10
    if data.get("why_now"):
        actionability += 8
    actionability = safe_score(data.get("sales_actionability_score"), actionability)
    final = (
        confidence * 0.20
        + source_quality * 0.20
        + pain * 0.25
        + dcover_fit * 0.25
        + actionability * 0.10
    )
    warnings = list(data.get("extraction_warnings") or [])
    missing = []
    if len(parties) < 2 and not data.get("court_or_regulator"):
        missing.append("clear parties or court/regulator")
        warnings.append("Parties or court/regulator are unclear.")
    if not data.get("source_url"):
        missing.append("source evidence")
    if not data.get("discovery_pain_summary"):
        missing.append("discovery pain summary")
    assets = sales_assets({**data, "discovery_pain_summary": data.get("discovery_pain_summary") or "likely discovery burden inferred from the matter type"})
    freshness = evaluate_freshness(data)
    scored_final = round(max(0, min(100, final)), 1)
    plan = sales_action_plan({**data, "final_trigger_score": scored_final, "discovery_pain_summary": data.get("discovery_pain_summary") or assets.get("sales_angle_one_liner")})
    return {
        **assets,
        **source_info,
        **freshness,
        **classify_litigation_trigger(data),
        "sales_action_plan": plan,
        "discovery_pain_summary": data.get("discovery_pain_summary") or "Likely discovery burden inferred from source trigger; verify exact document volume and deadlines before outreach.",
        "why_decoverai": data.get("why_decoverai") or "DecoverAI can help with document classification, responsiveness review, privilege review, redaction, Bates numbering, privilege logs, production setup, early case assessment, evidence analysis, and defensible audit trails.",
        "confidence_score": confidence,
        "source_quality_score": source_quality,
        "discovery_pain_score": pain,
        "dcover_fit_score": dcover_fit,
        "decover_fit_score": dcover_fit,
        "discovery_burden_score": pain,
        "sales_actionability_score": actionability,
        "final_trigger_score": scored_final,
        "scoring_breakdown": {
            "confidence": {"score": confidence, "weight": 20, "reason": "Factual clarity and extraction completeness."},
            "source_quality": {"score": source_quality, "weight": 20, "reason": "Credibility of source domain/publisher."},
            "discovery_pain": {"score": pain, "weight": 25, "reason": ", ".join(pain_reasons) or "Generic litigation signal."},
            "dcover_fit": {"score": dcover_fit, "weight": 25, "reason": ", ".join(fit_reasons) or "General fit for discovery workflow support."},
            "sales_actionability": {"score": actionability, "weight": 10, "reason": "Parties, evidence, timing, and usable outreach angle."},
        },
        "extraction_warnings": list(dict.fromkeys(warnings)),
        "missing_fields": list(dict.fromkeys(missing)),
    }

def get_thresholds(db: Session | None = None) -> dict:
    cfg = db.query(models.ScoringConfig).filter_by(is_active=True).first() if db else None
    min_discovery_pain = cfg.min_discovery_pain_score if cfg else settings.min_discovery_pain_score
    min_dcover_fit = cfg.min_dcover_fit_score if cfg else settings.min_dcover_fit_score
    return {
        "final_trigger_score": (cfg.final_trigger_threshold if cfg else settings.daily_trigger_threshold),
        "confidence_score": (cfg.min_confidence_score if cfg else settings.min_confidence_score),
        "source_quality_score": (cfg.min_source_quality_score if cfg else settings.min_source_quality_score),
        "discovery_pain_score": min(safe_score(min_discovery_pain, 55), 55),
        "dcover_fit_score": min(safe_score(min_dcover_fit, 55), 55),
        "sales_actionability_score": (cfg.min_sales_actionability_score if cfg else settings.min_sales_actionability_score),
        "max_daily_triggers": (cfg.max_daily_triggers if cfg else 50),
        "max_signal_age_days": (cfg.max_signal_age_days if cfg else settings.max_signal_age_days),
        "allow_unknown_signal_date": (cfg.allow_unknown_signal_date if cfg else False),
    }

def quality_gate(signal, db: Session | None = None) -> tuple[bool, str]:
    thresholds = get_thresholds(db)
    failures = []
    if not getattr(signal, "is_litigation_trigger", False):
        failures.append("not_litigation_trigger")
    freshness_status = getattr(signal, "freshness_status", "unknown") or "unknown"
    if freshness_status == "stale":
        failures.append("stale_signal")
    if freshness_status == "unknown" and not thresholds.get("allow_unknown_signal_date"):
        failures.append("unknown_date")
    if getattr(signal, "source_tier", "") == "blocked":
        failures.append("blocked_source")
    for field, threshold in thresholds.items():
        if field in {"max_daily_triggers", "max_signal_age_days", "allow_unknown_signal_date"}:
            continue
        if safe_score(getattr(signal, field, 0)) < safe_score(threshold):
            failures.append(f"{field} below {threshold}")
    parties = getattr(signal, "parties", None) or []
    if not parties:
        failures.append("no_clear_party")
    if not getattr(signal, "source_url", ""):
        failures.append("missing_source_evidence")
    pain = (getattr(signal, "discovery_pain_summary", "") or "").strip().lower()
    if (not pain or pain in {"likely discovery burden", "likely discovery burden inferred from the matter type"}) and safe_score(getattr(signal, "discovery_pain_score", 0)) < 50:
        failures.append("generic_discovery_pain")
    fit = (getattr(signal, "why_decoverai", "") or getattr(signal, "why_relevant_to_decoverAI", "") or "").lower()
    if (not fit or any(phrase in fit for phrase in GENERIC_FIT_PHRASES) or len(fit) < 80) and safe_score(getattr(signal, "dcover_fit_score", 0)) < 50:
        failures.append("generic_decoverai_fit")
    if getattr(signal, "status", "") == "rejected":
        failures.append("rejected")
    if "not_sales_actionable_regulator_item" in (getattr(signal, "gate_failure_reasons", None) or []):
        failures.append("not_sales_actionable_regulator_item")
    if getattr(signal, "duplicate_of_opportunity_id", None):
        failures.append("duplicate")
    failures = list(dict.fromkeys(failures))
    return (not failures), "Passed DecoverAI quality gate." if not failures else "; ".join(failures)

def apply_quality_to_signal(signal, db: Session | None = None):
    payload = {column.name: getattr(signal, column.name, None) for column in signal.__table__.columns}
    scored = score_signal_payload(payload)
    for key, value in scored.items():
        if hasattr(signal, key):
            setattr(signal, key, value)
    signal.why_decoverai = signal.why_decoverai or signal.why_relevant_to_decoverAI or "DecoverAI can help with classification, responsiveness review, privilege analysis, redaction, production setup, early case assessment, and defensible audit trails."
    signal.why_relevant_to_decoverAI = signal.why_relevant_to_decoverAI or signal.why_decoverai
    passed, reason = quality_gate(signal, db)
    signal.gate_passed = passed
    signal.gate_status = "passed" if passed else "failed"
    signal.gate_reason = reason
    signal.gate_failure_reasons = [] if passed else [x.strip() for x in reason.split(";") if x.strip()]
    return signal
