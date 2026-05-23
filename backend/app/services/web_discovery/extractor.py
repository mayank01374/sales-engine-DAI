from __future__ import annotations
import json, re
import httpx
from ...config import settings
from .. import infer_case_type_from_text, parse_case_parties
from .quality import score_signal_payload, source_quality_for

TRIGGER_HINTS = {
    "antitrust": ["antitrust", "monopoly", "competition"],
    "patent_ip": ["patent", "copyright", "trademark", "infringement"],
    "trade_secret": ["trade secret", "misappropriation", "source code"],
    "securities": ["securities", "shareholder", "10b-5", "sec "],
    "data_breach": ["data breach", "privacy", "cyber"],
    "regulatory_investigation": ["investigation", "enforcement", "regulator", "agency"],
    "employment_class_action": ["employment", "wage", "discrimination", "class action"],
    "ma_dispute": ["merger", "acquisition", "earnout", "m&a"],
    "contract_dispute": ["contract", "breach"],
    "mass_tort": ["mass tort", "product liability", "mdl"],
}

LAW_FIRM_PATTERN = re.compile(r"\b([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){0,3}\s+(?:LLP|LLC|P\.C\.|Law|Latham|Kirkland|Skadden|Cooley|Fenwick))\b")
COURT_PATTERN = re.compile(r"\b((?:U\.S\.\s+)?(?:District|Superior|Supreme|Chancery|Bankruptcy|Appeals?) Court[^.,;\n]*)", re.I)
REGULATOR_PATTERN = re.compile(r"\b(SEC|FTC|DOJ|Department of Justice|Federal Trade Commission|Securities and Exchange Commission|state attorney general)\b", re.I)

def _bounded(value, default=50):
    try:
        return max(0, min(100, float(value)))
    except Exception:
        return default

def _unique(matches):
    out = []
    for match in matches:
        value = " ".join(str(match).strip().split())
        if value and value not in out:
            out.append(value)
    return out[:10]

def _json(text: str):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    return json.loads(match.group(0) if match else cleaned)

def _fallback(text: str, metadata: dict):
    title = metadata.get("title") or "Untitled legal signal"
    combined = " ".join([title, metadata.get("snippet") or "", text or ""])
    lower = combined.lower()
    trigger_type = metadata.get("trigger_type") or "regulatory_investigation"
    for trigger, hints in TRIGGER_HINTS.items():
        if any(hint in lower for hint in hints):
            trigger_type = trigger
            break
    parties = parse_case_parties(title)
    if not parties:
        parties = _unique(re.findall(r"\b([A-Z][A-Za-z0-9&.'-]+(?:\s+[A-Z][A-Za-z0-9&.'-]+){0,3})\s+(?:sued|files|faces|settles|announces)", combined))[:6]
    law_firms = _unique(LAW_FIRM_PATTERN.findall(combined))
    courts = _unique(COURT_PATTERN.findall(combined))
    regulators = _unique(REGULATOR_PATTERN.findall(combined))
    burden = 58
    for kw, val in [("data breach", 90), ("trade secret", 92), ("antitrust", 92), ("class action", 86), ("patent", 82), ("securities", 84), ("source code", 90), ("documents", 76), ("emails", 82)]:
        if kw in lower:
            burden = max(burden, val)
    urgency = 82 if any(w in lower for w in ["filed", "new", "investigation", "complaint", "announced"]) else 62
    fit = round(burden * 0.7 + urgency * 0.2 + (75 if law_firms else 55) * 0.1, 1)
    confidence = 72 if len(text or "") > 500 else 55
    summary_source = metadata.get("snippet") or text[:500] or title
    matter_type = infer_case_type_from_text(combined)
    court_or_regulator = (courts or regulators or [""])[0]
    base = {
        "title": title,
        "source_url": metadata.get("url") or "",
        "source_domain": metadata.get("source_domain") or "",
        "publisher": metadata.get("publisher") or "",
        "published_at": metadata.get("published_at"),
        "matter_type": matter_type,
        "trigger_category": trigger_type,
        "trigger_type": trigger_type,
        "case_type": matter_type,
        "parties": parties,
        "party_roles": {},
        "law_firms": law_firms,
        "courts": courts,
        "regulators": regulators,
        "court_or_regulator": court_or_regulator,
        "jurisdiction": "US" if "u.s." in lower or "us " in lower or metadata.get("geography") == "US" else "",
        "summary": " ".join(summary_source.split())[:900],
        "factual_basis": " ".join((metadata.get("snippet") or text[:700] or title).split())[:1000],
        "discovery_pain_summary": "Likely discovery burden inferred from the matter type and source language. Verify exact volume and deadlines before outreach.",
        "why_now": "Recent public litigation or investigation signal captured from source evidence.",
        "why_decoverai": "DecoverAI may help with classification, responsiveness review, privilege analysis, redaction, production setup, early case assessment, and defensible audit trails.",
        "why_relevant_to_dcover": "DecoverAI may help with classification, responsiveness review, privilege analysis, redaction, production setup, early case assessment, and defensible audit trails.",
        "confidence_score": confidence,
        "source_quality_score": source_quality_for(metadata.get("url") or "", metadata.get("publisher") or ""),
        "discovery_pain_score": burden,
        "dcover_fit_score": fit,
        "sales_actionability_score": 0,
        "final_trigger_score": 0,
        "is_litigation_trigger": False,
        "trigger_relevance_reason": "",
        "extraction_warnings": [] if parties else ["Parties are unclear from fallback extraction."],
        "missing_fields": [],
    }
    return {**base, **score_signal_payload(base)}

def extract_signal_from_text(text: str, metadata: dict) -> dict:
    fallback = _fallback(text, metadata)
    if not settings.openai_api_key:
        return fallback
    schema = {
        "title": "string", "matter_type": "string", "trigger_category": "string", "parties": [], "party_roles": {},
        "law_firms": [], "court_or_regulator": "string", "jurisdiction": "string",
        "summary": "string", "factual_basis": "string", "discovery_pain_summary": "string",
        "why_now": "string", "why_decoverai": "string", "recommended_personas": [],
        "sales_angle_one_liner": "string", "email_subject": "string", "email_body": "string",
        "linkedin_message": "string", "call_opener": "string",
        "confidence_score": "0-100", "source_quality_score": "0-100", "discovery_pain_score": "0-100",
        "dcover_fit_score": "0-100", "sales_actionability_score": "0-100", "final_trigger_score": "0-100",
        "is_litigation_trigger": "boolean", "trigger_relevance_reason": "string",
        "gate_status": "passed|failed", "gate_failure_reasons": [],
        "extraction_warnings": [], "missing_fields": [],
    }
    prompt = {
        "instruction": "Extract only litigation or legal-market facts supported by the source text. Do not invent parties, law firms, courts, regulators, deadlines, or document volumes. Sales angles must be grounded in source evidence and DecoverAI capabilities: classification, responsiveness review, privilege analysis, confidentiality analysis, redaction, Bates numbering, privilege logs, production setup, early case assessment, chronology/evidence analysis, audit trails, fast production, and lower review cost. Use 'likely discovery burden' only for inference.",
        "metadata": metadata,
        "schema": schema,
        "text": text[:20000],
    }
    try:
        body = {
            "model": settings.openai_model,
            "messages": [{"role": "user", "content": json.dumps(prompt)}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=30) as client:
            response = client.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {settings.openai_api_key}"}, json=body)
            response.raise_for_status()
            result = _json(response.json()["choices"][0]["message"]["content"])
        for key in ["parties", "law_firms", "courts", "regulators", "recommended_personas", "extraction_warnings", "missing_fields"]:
            result[key] = result.get(key) if isinstance(result.get(key), list) else []
        for key in ["confidence_score", "source_quality_score", "discovery_pain_score", "dcover_fit_score", "sales_actionability_score", "final_trigger_score"]:
            result[key] = _bounded(result.get(key), fallback[key])
        result = {**fallback, **result}
        return {**result, **score_signal_payload(result)}
    except Exception:
        return fallback
