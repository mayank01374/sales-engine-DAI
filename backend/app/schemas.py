from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Any

STATUSES = ["New", "Researching", "Qualified", "Contacted", "Not Relevant", "Won", "Lost"]

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}

class ErrorResponse(BaseModel):
    error: ErrorDetail

class EvidenceOut(BaseModel):
    id: int
    source_url: str
    source_title: str
    publisher: str
    published_at: datetime | None = None
    snippet: str
    evidence_type: str
    credibility_score: float
    source_tier: str = "low_quality"
    source_reason: str = ""
    created_at: datetime
    @field_validator("source_tier", "source_reason", mode="before")
    @classmethod
    def _none_to_string(cls, value):
        return "" if value is None else value
    class Config: from_attributes=True

class OpportunityBase(BaseModel):
    case_name: str
    trigger_type: str = "New Lawsuit"
    case_type: str = "Unknown"
    parties: list[str] = []
    law_firms: list[str] = []
    summary: str = ""
    notes: str = ""

class OpportunityCreate(OpportunityBase):
    source_url: str | None = None
    source_title: str | None = None
    snippet: str | None = None

class OpportunityOut(OpportunityBase):
    id: int
    status: str
    matter_type: str = ""
    trigger_category: str = ""
    party_roles: dict[str, Any] = {}
    court_or_regulator: str = ""
    jurisdiction: str = ""
    factual_basis: str = ""
    discovery_pain_summary: str = ""
    why_now: str = ""
    why_decoverai: str = ""
    recommended_personas: list[str] = []
    sales_angle_one_liner: str = ""
    email_subject: str = ""
    email_body: str = ""
    linkedin_message: str = ""
    call_opener: str = ""
    score: float
    confidence_score: float = 0
    source_quality_score: float = 0
    discovery_pain_score: float = 0
    dcover_fit_score: float = 0
    sales_actionability_score: float = 0
    final_trigger_score: float = 0
    extraction_warnings: list[str] = []
    missing_fields: list[str] = []
    discovery_burden_score: float
    urgency_score: float
    decoverAI_fit_score: float
    company_size_score: float
    law_firm_signal_score: float
    freshness_score: float
    case_type_score: float
    scoring_breakdown: dict[str, Any]
    recommended_persona: str
    pitch_angle: str
    generated_email: str
    enrichment_status: str
    created_at: datetime
    updated_at: datetime
    evidence: list[EvidenceOut] = []
    class Config: from_attributes=True

class OpportunityListResponse(BaseModel):
    items: list[OpportunityOut]
    total: int
    page: int
    page_size: int

class StatusUpdate(BaseModel):
    status: str

class NotesUpdate(BaseModel):
    notes: str

class ResearchTaskCreate(BaseModel):
    task_type: str

class ResearchTaskOut(BaseModel):
    id: int
    opportunity_id: int
    task_type: str
    status: str
    input_payload: dict[str, Any]
    output_payload: dict[str, Any]
    error_message: str
    created_at: datetime
    updated_at: datetime
    class Config: from_attributes=True

class ContactOut(BaseModel):
    id: int
    persona: str
    title_keywords: list[str]
    why_relevant: str
    outreach_priority: int
    confidence_score: float
    created_at: datetime
    class Config: from_attributes=True

class AccountOut(BaseModel):
    id: int
    opportunity_id: int
    entity_name: str
    entity_type: str
    website: str
    industry: str
    company_size_band: str
    geography: str
    description: str
    likely_data_sources: list[str]
    legal_team_signal: str
    enrichment_status: str
    confidence_score: float
    contacts: list[ContactOut] = []
    created_at: datetime
    updated_at: datetime
    class Config: from_attributes=True

class ScoringConfigIn(BaseModel):
    case_type_weight: float = 20
    discovery_burden_weight: float = 25
    company_size_weight: float = 15
    urgency_weight: float = 15
    law_firm_signal_weight: float = 10
    freshness_weight: float = 5
    decoverAI_fit_weight: float = 10
    confidence_weight: float = 20
    source_quality_weight: float = 20
    discovery_pain_quality_weight: float = 25
    dcover_fit_weight: float = 25
    sales_actionability_weight: float = 10
    final_trigger_threshold: float = 75
    min_confidence_score: float = 70
    min_source_quality_score: float = 65
    min_discovery_pain_score: float = 70
    min_dcover_fit_score: float = 70
    min_sales_actionability_score: float = 75
    source_allowlist: str = ""
    source_blocklist: str = ""
    discovery_query_settings: dict[str, Any] = {}

class ScoringConfigOut(ScoringConfigIn):
    id: int
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    class Config: from_attributes=True

class SettingsOut(BaseModel):
    final_trigger_score_min: int = 70
    confidence_score_min: int = 60
    source_quality_score_min: int = 50
    discovery_pain_score_min: int = 60
    dcover_fit_score_min: int = 60
    max_daily_triggers: int = 50
    max_signal_age_days: int = 90
    allow_unknown_signal_date: bool = False
    max_per_source_domain: int = 4
    max_per_trigger_category: int = 5
    max_per_same_party: int = 2
    trusted_domains: str = ""
    blocked_domains: str = ""
    default_time_range: str = "week"
    default_max_results: int = 40
    source_packs: list[dict[str, Any]] = []
    enable_demo_data: bool = False

class SettingsUpdate(BaseModel):
    final_trigger_score_min: int = 70
    confidence_score_min: int = 60
    source_quality_score_min: int = 50
    discovery_pain_score_min: int = 60
    dcover_fit_score_min: int = 60
    max_daily_triggers: int = 50
    max_signal_age_days: int = Field(default=90, ge=1, le=730)
    allow_unknown_signal_date: bool = False
    max_per_source_domain: int = Field(default=4, ge=1, le=20)
    max_per_trigger_category: int = Field(default=5, ge=1, le=20)
    max_per_same_party: int = Field(default=2, ge=1, le=20)
    trusted_domains: str = ""
    blocked_domains: str = ""
    default_time_range: str = Field(default="week", pattern="^(day|week|month|year)$")
    default_max_results: int = Field(default=40, ge=1, le=100)
    source_packs: list[dict[str, Any]] = []

class QualitySummaryOut(BaseModel):
    last_run_status: str | None = None
    total_raw_signals: int = 0
    passed_gate: int = 0
    failed_gate: int = 0
    converted: int = 0
    top_failure_reasons: list[dict[str, Any]] = []
    top_source_domains: list[dict[str, Any]] = []
    useful_rate: float = 0
    top_bad_source_domains: list[dict[str, Any]] = []
    top_good_source_domains: list[dict[str, Any]] = []
    best_trigger_categories: list[dict[str, Any]] = []
    common_rejection_reasons: list[dict[str, Any]] = []

class LLMStatusOut(BaseModel):
    configured: bool
    ok: bool
    provider: str
    model: str
    message: str

class CampaignCreate(BaseModel):
    name: str
    description: str = ""
    target_segment: str = ""
    owner_name: str = "Sales"
    status: str = "active"

class CampaignOut(CampaignCreate):
    id: int
    opportunity_count: int = 0
    average_score: float = 0
    created_at: datetime
    updated_at: datetime
    class Config: from_attributes=True

class SavedViewCreate(BaseModel):
    name: str
    filters: dict[str, Any] = {}
    sort: dict[str, Any] = {}
    is_default: bool = False

class SavedViewOut(SavedViewCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    class Config: from_attributes=True

class ActivityOut(BaseModel):
    id: int
    opportunity_id: int
    actor_name: str
    activity_type: str
    message: str
    metadata_json: dict[str, Any]
    created_at: datetime
    class Config: from_attributes=True

TRIGGER_TYPES = [
    "all",
    "antitrust", "patent_ip", "trade_secret", "securities", "data_breach",
    "regulatory_investigation", "employment_class_action", "ma_dispute",
    "contract_dispute", "mass_tort",
]
DISCOVERY_STATUSES = ["pending", "running", "completed", "failed"]
SIGNAL_STATUSES = ["new", "reviewed", "converted", "rejected"]

class WebDiscoveryRunCreate(BaseModel):
    trigger_type: str = Field(default="all", pattern="^(all|antitrust|patent_ip|trade_secret|securities|data_breach|regulatory_investigation|healthcare_fraud_white_collar|commercial_litigation|construction_defect|employment_class_action|ma_dispute|contract_dispute|mass_tort)$")
    time_range: str = Field(default="week", pattern="^(day|week|month|year)$")
    max_results: int = Field(default=40, ge=1, le=100)
    include_domains: list[str] = []
    exclude_domains: list[str] = []
    dry_run: bool = False

class ScrapeAttemptOut(BaseModel):
    id: int
    discovered_signal_id: int
    provider: str
    status: str
    http_status: int | None = None
    error_message: str
    robots_allowed: bool
    duration_ms: int
    created_at: datetime
    class Config: from_attributes=True

class DiscoveredSignalOut(BaseModel):
    id: int
    discovery_run_id: int | None = None
    title: str
    source_url: str
    source_domain: str
    publisher: str
    published_at: datetime | None = None
    signal_date: datetime | None = None
    signal_age_days: int | None = None
    freshness_status: str = "unknown"
    freshness_reason: str = ""
    source_tier: str = "low_quality"
    source_reason: str = ""
    raw_snippet: str
    scraped_text_preview: str = ""
    trigger_type: str
    case_type: str
    matter_type: str = ""
    trigger_category: str = ""
    parties: list[str]
    party_roles: dict[str, Any] = {}
    law_firms: list[str]
    courts: list[str]
    regulators: list[str]
    court_or_regulator: str = ""
    jurisdiction: str = ""
    summary: str
    factual_basis: str = ""
    discovery_pain_summary: str = ""
    why_now: str = ""
    why_decoverai: str = ""
    why_relevant_to_decoverAI: str
    recommended_personas: list[str] = []
    sales_angle_one_liner: str = ""
    email_subject: str = ""
    email_body: str = ""
    linkedin_message: str = ""
    call_opener: str = ""
    sales_action_plan: dict[str, Any] = {}
    discovery_burden_score: float
    urgency_score: float
    decover_fit_score: float
    confidence_score: float
    source_quality_score: float = 0
    discovery_pain_score: float = 0
    dcover_fit_score: float = 0
    sales_actionability_score: float = 0
    final_trigger_score: float = 0
    extraction_warnings: list[str] = []
    missing_fields: list[str] = []
    is_litigation_trigger: bool = False
    trigger_relevance_reason: str = ""
    gate_status: str = "failed"
    gate_failure_reasons: list[str] = []
    duplicate_confidence: float = 0
    gate_passed: bool = False
    gate_reason: str = ""
    rejection_reason: str = ""
    duplicate_reason: str = ""
    duplicate_of_opportunity_id: int | None = None
    status: str
    sales_review_status: str = ""
    sales_review_reason: str = ""
    sales_review_notes: str = ""
    scrape_attempts: list[ScrapeAttemptOut] = []
    created_at: datetime
    updated_at: datetime
    @field_validator(
        "freshness_status", "freshness_reason", "source_tier", "source_reason",
        "sales_review_status", "sales_review_reason", "sales_review_notes",
        mode="before",
    )
    @classmethod
    def _none_to_string(cls, value):
        return "" if value is None else value

    @field_validator("sales_action_plan", mode="before")
    @classmethod
    def _none_to_dict(cls, value):
        return {} if value is None else value
    class Config: from_attributes=True

class DiscoveredSignalDetailOut(DiscoveredSignalOut):
    scraped_text: str = ""
    class Config: from_attributes=True

class WebDiscoveryRunOut(BaseModel):
    id: int
    query: str
    trigger_type: str
    geography: str
    industry: str
    time_range: str
    status: str
    total_results: int
    converted_count: int
    error_message: str
    created_at: datetime
    updated_at: datetime
    class Config: from_attributes=True

class DiscoveredSignalStatusUpdate(BaseModel):
    status: str = Field(pattern="^(new|reviewed|rejected|qualified|contacted|needs_more_research)$")
    rejection_reason: str = ""

class SalesReviewUpdate(BaseModel):
    review_status: str = Field(pattern="^(useful|not_useful|needs_research)$")
    reason: str = Field(pattern="^(wrong_source|too_old|unclear_party|weak_discovery_pain|not_decoverai_fit|no_clear_buyer|duplicate|good_trigger|good_sales_angle|contacted)$")
    notes: str = ""

class DailyTriggerResponse(BaseModel):
    items: list[DiscoveredSignalOut]
    total: int
    page: int
    page_size: int
