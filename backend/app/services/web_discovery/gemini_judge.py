from __future__ import annotations
import json, re
import httpx
from ...config import settings
from .quality import safe_score

def _parse_json(text: str) -> dict:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    return json.loads(match.group(0) if match else cleaned)

def gemini_configured() -> bool:
    return bool(settings.gemini_api_key)

def check_gemini() -> dict:
    if not settings.gemini_api_key:
        return {"configured": False, "ok": False, "provider": "gemini", "model": settings.gemini_model, "message": "GEMINI_API_KEY is not configured."}
    try:
        result = _call_gemini({"task": "health_check", "instruction": "Return JSON only.", "response_format": {"ok": True}})
        return {"configured": True, "ok": bool(result), "provider": "gemini", "model": settings.gemini_model, "message": "Gemini responded."}
    except Exception as exc:
        return {"configured": True, "ok": False, "provider": "gemini", "model": settings.gemini_model, "message": str(exc)}

def _call_gemini(prompt: dict) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": json.dumps(prompt)}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    with httpx.Client(timeout=30) as client:
        response = client.post(url, headers={"x-goog-api-key": settings.gemini_api_key}, json=body)
        response.raise_for_status()
        payload = response.json()
    return _parse_json(payload["candidates"][0]["content"]["parts"][0]["text"])

def judge_signal_with_gemini(signal) -> dict | None:
    if not settings.gemini_api_key:
        return None
    prompt = {
        "task": "Decide whether DecoverAI sales should pursue this public litigation signal.",
        "product": {
            "name": "DecoverAI",
            "capabilities": [
                "document classification", "responsiveness review", "privilege review",
                "redaction", "Bates numbering", "privilege logs", "production setup",
                "early case assessment", "chronology/evidence analysis", "audit trail",
                "high-volume discovery",
            ],
        },
        "rules": [
            "Do not invent parties, law firms, courts, regulators, deadlines, or document volume.",
            "Pursue only actionable litigation, investigation, charges, complaint, class action, settlement, subpoena, or production-related matters.",
            "Reject generic policy statements, guidance, rulemaking, annual reports, commentary, and pages without a named matter or actor.",
            "Use likely only for inference.",
            "Every sales angle must connect to concrete DecoverAI capabilities.",
        ],
        "signal": {
            "title": signal.title,
            "source_url": signal.source_url,
            "source_domain": signal.source_domain,
            "publisher": signal.publisher,
            "published_at": str(signal.published_at) if signal.published_at else None,
            "raw_snippet": signal.raw_snippet,
            "scraped_text_preview": (signal.scraped_text or "")[:6000],
            "matter_type": signal.matter_type,
            "trigger_category": signal.trigger_category,
            "parties": signal.parties or [],
            "law_firms": signal.law_firms or [],
            "court_or_regulator": signal.court_or_regulator,
            "summary": signal.summary,
            "discovery_pain_summary": signal.discovery_pain_summary,
            "why_decoverai": signal.why_decoverai,
        },
        "response_schema": {
            "should_pursue": "boolean",
            "is_litigation_trigger": "boolean",
            "trigger_relevance_reason": "string",
            "gate_status": "passed|failed",
            "gate_failure_reasons": ["string"],
            "confidence_score": "0-100",
            "source_quality_score": "0-100",
            "discovery_pain_score": "0-100",
            "dcover_fit_score": "0-100",
            "sales_actionability_score": "0-100",
            "final_trigger_score": "0-100",
            "summary": "string",
            "factual_basis": "string",
            "discovery_pain_summary": "string",
            "why_now": "string",
            "why_decoverai": "string",
            "recommended_personas": ["string"],
            "sales_angle_one_liner": "string",
            "email_subject": "string",
            "email_body": "string",
            "linkedin_message": "string",
            "call_opener": "string",
            "extraction_warnings": ["string"],
            "missing_fields": ["string"],
        },
    }
    result = _call_gemini(prompt)
    for key in ["confidence_score", "source_quality_score", "discovery_pain_score", "dcover_fit_score", "sales_actionability_score", "final_trigger_score"]:
        result[key] = safe_score(result.get(key), 0)
    for key in ["gate_failure_reasons", "recommended_personas", "extraction_warnings", "missing_fields"]:
        result[key] = result.get(key) if isinstance(result.get(key), list) else []
    result["should_pursue"] = bool(result.get("should_pursue"))
    result["is_litigation_trigger"] = bool(result.get("is_litigation_trigger"))
    result["gate_status"] = "passed" if result["should_pursue"] and result.get("gate_status") == "passed" else "failed"
    return result

def apply_gemini_judgment(signal) -> bool:
    result = judge_signal_with_gemini(signal)
    if not result:
        return False
    signal.is_litigation_trigger = result["is_litigation_trigger"]
    signal.trigger_relevance_reason = result.get("trigger_relevance_reason") or signal.trigger_relevance_reason
    signal.gate_status = result["gate_status"]
    signal.gate_passed = result["gate_status"] == "passed"
    signal.gate_failure_reasons = result.get("gate_failure_reasons") or ([] if signal.gate_passed else ["gemini_rejected"])
    signal.gate_reason = "Gemini passed this signal for sales pursuit." if signal.gate_passed else "; ".join(signal.gate_failure_reasons)
    for field in ["summary", "factual_basis", "discovery_pain_summary", "why_now", "why_decoverai", "sales_angle_one_liner", "email_subject", "email_body", "linkedin_message", "call_opener"]:
        if result.get(field):
            setattr(signal, field, result[field])
    signal.why_relevant_to_decoverAI = signal.why_decoverai
    signal.recommended_personas = result.get("recommended_personas") or signal.recommended_personas or []
    signal.extraction_warnings = result.get("extraction_warnings") or signal.extraction_warnings or []
    signal.missing_fields = result.get("missing_fields") or signal.missing_fields or []
    signal.confidence_score = result["confidence_score"]
    signal.source_quality_score = result["source_quality_score"]
    signal.discovery_pain_score = result["discovery_pain_score"]
    signal.discovery_burden_score = result["discovery_pain_score"]
    signal.dcover_fit_score = result["dcover_fit_score"]
    signal.decover_fit_score = result["dcover_fit_score"]
    signal.sales_actionability_score = result["sales_actionability_score"]
    signal.final_trigger_score = result["final_trigger_score"]
    return True
