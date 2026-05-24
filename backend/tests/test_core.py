from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone

from app.db import Base
from app import models
from app.main import app
from app.db import get_db
from app.services import normalize_key, split_list
from app.services import active_config
from app.services import seed
from app.services.web_discovery.query_builder import build_discovery_queries
from app.services.web_discovery.extractor import extract_signal_from_text
from app.services.web_discovery.dedupe import dedupe_signal
from app.services.web_discovery.runner import convert_signal_to_opportunity, _is_recent_search_result
from app.services.web_discovery.quality import score_signal_payload, quality_gate, apply_quality_to_signal
from app.services.web_discovery.quality import safe_score
from app.services.web_discovery.source_packs import default_source_packs, enabled_source_packs
from app.services.web_discovery.runner import run_discovery
from app.services.web_discovery.runner import _search_provider
from app.services.web_search.composite_provider import CompositeSearchProvider
from app.services.web_search.courtlistener_provider import CourtListenerSearchProvider
from app.services.web_search.tavily_provider import TavilySearchProvider
from app.services.web_search.base import WebSearchResult
from app.services.scraping.firecrawl_provider import FirecrawlScraperProvider
from app.services.scraping import robots

def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()

def test_normalize_key():
    assert normalize_key("A v. B", ["A","B"], "New Lawsuit").startswith("a-v-b")

def test_split_list():
    assert split_list("A; B, C") == ["A","B","C"]

def test_web_discovery_query_builder():
    queries = build_discovery_queries("trade_secret", "US", "AI")
    assert any("trade secret" in q for q in queries)

def test_web_discovery_query_builder_uses_enabled_source_packs():
    packs = default_source_packs()
    packs[0]["enabled"] = False
    queries = build_discovery_queries("data_breach", "US", "", enabled_source_packs(packs))
    assert any("site:reuters.com/legal" in q for q in queries)
    assert not any(q.startswith("site:courtlistener.com") for q in queries)

def test_web_discovery_all_queries_cover_sales_categories():
    queries = build_discovery_queries("all", "US", "technology")
    joined = " ".join(queries).lower()
    assert "data breach" in joined
    assert "securities class action" in joined
    assert "antitrust lawsuit" in joined
    assert "trade secret" in joined
    assert "healthcare fraud" in joined
    assert "technology" not in joined

def test_discovery_search_provider_includes_courtlistener(monkeypatch):
    monkeypatch.setattr("app.services.web_discovery.runner.settings.tavily_api_key", None)
    provider = _search_provider()
    assert isinstance(provider, CompositeSearchProvider)
    assert any(isinstance(p, CourtListenerSearchProvider) for p in provider.providers)

def test_courtlistener_parses_date_only_date_filed(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"results": [{
                "caseName": "Acme v. Globex",
                "docket_absolute_url": "/docket/123/acme-v-globex/",
                "dateFiled": "2024-05-24",
                "snippet": "Complaint filed.",
            }]}
    class Client:
        def __init__(self, timeout, headers): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr("app.services.web_search.courtlistener_provider.httpx.Client", Client)
    result = CourtListenerSearchProvider().search("acme", 1)[0]
    assert result.published_at is not None
    assert result.published_at.date().isoformat() == "2024-05-24"

def test_courtlistener_parses_nested_recap_entry_date(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"results": [{
                "caseName": "Acme v. Globex",
                "docket_absolute_url": "/docket/123/acme-v-globex/",
                "dateFiled": None,
                "snippet": "Complaint filed.",
                "recap_documents": [
                    {"absolute_url": "/recap/gov.uscourts/old.pdf", "entry_date_filed": "2024-01-01"},
                    {"absolute_url": "/recap/gov.uscourts/new.pdf", "entry_date_filed": "2026-05-01"},
                ],
            }]}
    class Client:
        def __init__(self, timeout, headers): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr("app.services.web_search.courtlistener_provider.httpx.Client", Client)
    result = CourtListenerSearchProvider().search("acme", 1)[0]
    assert result.published_at is not None
    assert result.published_at.date().isoformat() == "2026-05-01"
    assert result.published_at.tzinfo is not None

def test_courtlistener_handles_mixed_timezone_dates(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"results": [{
                "caseName": "Acme v. Globex",
                "docket_absolute_url": "/docket/123/acme-v-globex/",
                "dateFiled": "2026-04-30T12:00:00-04:00",
                "snippet": "Complaint filed.",
                "recap_documents": [
                    {"absolute_url": "/recap/gov.uscourts/new.pdf", "entry_date_filed": "2026-05-01"},
                ],
            }]}
    class Client:
        def __init__(self, timeout, headers): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr("app.services.web_search.courtlistener_provider.httpx.Client", Client)
    result = CourtListenerSearchProvider().search("acme", 1)[0]
    assert result.published_at is not None
    assert result.published_at.date().isoformat() == "2026-05-01"
    assert result.published_at.tzinfo is not None

def test_tavily_provider_passes_time_range_days(monkeypatch):
    captured = {}
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"results": []}
    class Client:
        def __init__(self, timeout): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, json):
            captured["payload"] = json
            return Response()
    monkeypatch.setattr("app.services.web_search.tavily_provider.httpx.Client", Client)
    TavilySearchProvider(api_key="test").search("query", 5, time_range="month")
    assert captured["payload"]["topic"] == "news"
    assert captured["payload"]["days"] == 30

def test_firecrawl_returns_structured_published_at(monkeypatch):
    class Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"data": {"metadata": {"title": "Acme article", "publishedTime": "May 1, 2026"}, "markdown": "Article body"}}
    class Client:
        def __init__(self, timeout): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs): return Response()
    monkeypatch.setattr("app.services.scraping.firecrawl_provider.httpx.Client", Client)
    result = FirecrawlScraperProvider(api_key="test").scrape("https://www.reuters.com/legal/acme")
    assert result.published_at == "May 1, 2026"
    assert result.markdown_or_text.startswith("Published at: May 1, 2026")

def test_gemini_judgment_can_override_gate(monkeypatch):
    db = session()
    from app.services.web_discovery import runner
    class Provider:
        def search(self, *args, **kwargs):
            from app.services.web_search.base import WebSearchResult
            return [WebSearchResult(title="Generic policy update", url="https://www.sec.gov/policy", domain="sec.gov", snippet="Policy statement guidance.", published_at=datetime.now(timezone.utc) - timedelta(days=5))]
    monkeypatch.setattr(runner, "_search_provider", lambda: Provider())
    monkeypatch.setattr(runner, "_scrapers", lambda: [])
    monkeypatch.setattr(runner, "apply_gemini_judgment", lambda signal: setattr(signal, "gate_passed", True) or setattr(signal, "gate_status", "passed") or setattr(signal, "is_litigation_trigger", True) or setattr(signal, "gate_failure_reasons", []) or True)
    run = runner.run_discovery(db, "all", max_results=1, dry_run=True)
    signal = db.query(models.DiscoveredSignal).first()
    assert run.status == "completed"
    assert signal.gate_passed

def test_extractor_fallback_fact_grounded(monkeypatch):
    monkeypatch.setattr("app.services.web_discovery.extractor.settings.openai_api_key", None)
    monkeypatch.setattr("app.services.web_discovery.extractor.settings.groq_api_key", None)
    result = extract_signal_from_text(
        "Acme sued Globex for trade secret misappropriation involving source code and internal documents.",
        {"title": "Acme v. Globex trade secret lawsuit", "snippet": "Complaint filed this week."},
    )
    assert result["trigger_type"] == "trade_secret"
    assert result["discovery_burden_score"] >= 90
    assert "Acme" in result["parties"]

def test_extractor_keeps_openai_published_date(monkeypatch):
    monkeypatch.setattr("app.services.web_discovery.extractor.settings.openai_api_key", "test")
    monkeypatch.setattr("app.services.web_discovery.extractor.settings.groq_api_key", None)
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": '{"title":"Acme lawsuit filed","parties":["Acme"],"published_at":"2026-05-01T00:00:00+00:00","summary":"A lawsuit was filed against Acme.","discovery_pain_summary":"Likely document production and privilege review.","why_decoverai":"DecoverAI can help classify documents, accelerate privilege review, support redaction, and prepare defensible production.","is_litigation_trigger":true}'}}]}
    class Client:
        def __init__(self, timeout): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs): return Response()
    monkeypatch.setattr("app.services.web_discovery.extractor.httpx.Client", Client)
    result = extract_signal_from_text("Published on May 1, 2026. A lawsuit was filed against Acme.", {"title": "Acme lawsuit", "url": "https://www.reuters.com/legal/acme"})
    assert str(result["published_at"]).startswith("2026-05-01")
    assert result["freshness_status"] == "fresh"

def test_extractor_serializes_datetime_metadata(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.services.web_discovery.extractor.settings.openai_api_key", "test")
    monkeypatch.setattr("app.services.web_discovery.extractor.settings.groq_api_key", None)
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": '{"title":"Acme lawsuit filed","parties":["Acme"],"summary":"A lawsuit was filed against Acme.","discovery_pain_summary":"Likely document production and privilege review.","why_decoverai":"DecoverAI can help classify documents, accelerate privilege review, support redaction, and prepare defensible production.","is_litigation_trigger":true}'}}]}
    class Client:
        def __init__(self, timeout): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, headers, json):
            captured["content"] = json["messages"][0]["content"]
            return Response()
    monkeypatch.setattr("app.services.web_discovery.extractor.httpx.Client", Client)
    extract_signal_from_text("A lawsuit was filed against Acme.", {"title": "Acme lawsuit", "url": "https://www.reuters.com/legal/acme", "published_at": datetime(2026, 5, 1, tzinfo=timezone.utc)})
    assert "2026-05-01T00:00:00+00:00" in captured["content"]

def test_extractor_accepts_human_readable_published_date(monkeypatch):
    monkeypatch.setattr("app.services.web_discovery.extractor.settings.openai_api_key", "test")
    monkeypatch.setattr("app.services.web_discovery.extractor.settings.groq_api_key", None)
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": '{"title":"Acme lawsuit filed","parties":["Acme"],"published_at":"May 1, 2026","summary":"A lawsuit was filed against Acme.","discovery_pain_summary":"Likely document production and privilege review.","why_decoverai":"DecoverAI can help classify documents, accelerate privilege review, support redaction, and prepare defensible production.","is_litigation_trigger":true}'}}]}
    class Client:
        def __init__(self, timeout): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs): return Response()
    monkeypatch.setattr("app.services.web_discovery.extractor.httpx.Client", Client)
    result = extract_signal_from_text("Published May 1, 2026. A lawsuit was filed against Acme.", {"title": "Acme lawsuit", "url": "https://www.reuters.com/legal/acme"})
    assert str(result["published_at"]).startswith("2026-05-01")
    assert result["freshness_status"] == "fresh"
    assert result["published_at"].tzinfo is not None

def test_extractor_falls_back_to_timezone_aware_metadata_date(monkeypatch):
    monkeypatch.setattr("app.services.web_discovery.extractor.settings.openai_api_key", "test")
    monkeypatch.setattr("app.services.web_discovery.extractor.settings.groq_api_key", None)
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": '{"title":"Acme lawsuit filed","parties":["Acme"],"published_at":"unknown","summary":"A lawsuit was filed against Acme.","discovery_pain_summary":"Likely document production and privilege review.","why_decoverai":"DecoverAI can help classify documents, accelerate privilege review, support redaction, and prepare defensible production.","is_litigation_trigger":true}'}}]}
    class Client:
        def __init__(self, timeout): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs): return Response()
    monkeypatch.setattr("app.services.web_discovery.extractor.httpx.Client", Client)
    result = extract_signal_from_text("A lawsuit was filed against Acme.", {"title": "Acme lawsuit", "url": "https://www.reuters.com/legal/acme", "published_at": datetime(2026, 5, 1)})
    assert result["published_at"].tzinfo is not None

def test_extractor_uses_groq_when_configured(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.services.web_discovery.extractor.settings.groq_api_key", "groq-test")
    monkeypatch.setattr("app.services.web_discovery.extractor.settings.groq_model", "llama-test")
    monkeypatch.setattr("app.services.web_discovery.extractor.settings.openai_api_key", None)
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": '{"title":"Acme lawsuit filed","parties":["Acme"],"summary":"A lawsuit was filed against Acme.","discovery_pain_summary":"Likely document production and privilege review.","why_decoverai":"DecoverAI can help classify documents, accelerate privilege review, support redaction, and prepare defensible production.","is_litigation_trigger":true}'}}]}
    class Client:
        def __init__(self, timeout): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, headers, json):
            captured["url"] = url
            captured["auth"] = headers["Authorization"]
            captured["model"] = json["model"]
            return Response()
    monkeypatch.setattr("app.services.web_discovery.extractor.httpx.Client", Client)
    extract_signal_from_text("A lawsuit was filed against Acme.", {"title": "Acme lawsuit", "url": "https://www.reuters.com/legal/acme"})
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["auth"] == "Bearer groq-test"
    assert captured["model"] == "llama-test"

def test_dedupe_exact_url():
    db = session()
    opp = models.Opportunity(case_name="Acme v. Globex", normalized_key="acme-v-globex", trigger_type="trade_secret")
    db.add(opp); db.flush()
    db.add(models.SourceEvidence(opportunity_id=opp.id, source_url="https://example.com/case", source_title="Acme v. Globex"))
    signal = models.DiscoveredSignal(discovery_run_id=1, title="Acme v. Globex", source_url="https://example.com/case", parties=["Acme", "Globex"])
    db.add(signal); db.flush()
    assert dedupe_signal(db, signal) == opp.id

def test_convert_discovered_signal_to_opportunity():
    db = session()
    db.add(models.ScoringConfig(name="Default", is_active=True))
    run = models.WebDiscoveryRun(query="q", trigger_type="data_breach")
    db.add(run); db.flush()
    signal = models.DiscoveredSignal(
        discovery_run_id=run.id,
        title="Customers v. Acme data breach class action",
        source_url="https://example.com/breach",
        raw_snippet="A data breach class action was filed.",
        trigger_type="data_breach",
        case_type="Data Breach",
        parties=["Customers", "Acme"],
        summary="A data breach class action was filed.",
        confidence_score=80,
        source_quality_score=88,
        discovery_pain_score=90,
        dcover_fit_score=88,
        sales_actionability_score=86,
        final_trigger_score=86,
        gate_passed=True,
        is_litigation_trigger=True,
        published_at=datetime.now(timezone.utc) - timedelta(days=30),
        signal_date=datetime.now(timezone.utc) - timedelta(days=30),
        signal_age_days=30,
        freshness_status="fresh",
        discovery_pain_summary="Likely redaction, privilege review, document classification, and production burden.",
        why_decoverai="DecoverAI can help classify documents, identify responsive materials, accelerate privilege review, support redaction, create privilege logs, and prepare defensible production with audit trails.",
    )
    db.add(signal); db.flush()
    opp = convert_signal_to_opportunity(db, signal)
    db.commit()
    assert signal.status == "converted"
    assert opp.evidence[0].source_url == "https://example.com/breach"

def test_manual_courtlistener_ingest_preserves_evidence_date(monkeypatch):
    db = session()
    db.add(models.ScoringConfig(name="Default", is_active=True))
    from app import services
    monkeypatch.setattr(services, "validate_signal_with_gemini", lambda data: {"useful": True, "reason": "test"})
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"results": [{
                "caseName": "Acme v. Globex",
                "docket_absolute_url": "/docket/123/acme-v-globex/",
                "dateFiled": None,
                "snippet": "Complaint filed in trade secret lawsuit involving documents.",
                "party": ["Acme", "Globex"],
                "recap_documents": [
                    {"absolute_url": "/recap/gov.uscourts/new.pdf", "entry_date_filed": "2026-05-01"},
                ],
            }]}
    class Client:
        def __init__(self, timeout, headers): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr("app.services.httpx.Client", Client)
    result = services.ingest_courtlistener(db, "acme", page_size=1)
    assert result["count"] == 1
    evidence = db.query(models.SourceEvidence).first()
    assert evidence.published_at is not None
    assert evidence.published_at.date().isoformat() == "2026-05-01"

def test_no_dummy_data_loaded_by_default(monkeypatch):
    monkeypatch.setattr("app.services.settings.enable_demo_data", False)
    db = session()
    seed(db)
    assert db.query(models.Opportunity).count() == 0
    assert db.query(models.Campaign).count() == 0
    assert db.query(models.SavedView).count() == 0

def test_demo_data_gates_advanced_seed(monkeypatch):
    monkeypatch.setattr("app.services.settings.enable_demo_data", True)
    db = session()
    seed(db)
    assert db.query(models.Campaign).count() > 0
    assert db.query(models.SavedView).count() > 0

def test_decoverai_scoring_formula_and_sales_angle():
    scored = score_signal_payload({
        "title": "Acme v. Globex data breach class action",
        "source_url": "https://www.sec.gov/news/test",
        "parties": ["Acme", "Globex"],
        "matter_type": "Data Breach",
        "trigger_category": "data_breach",
        "summary": "Class action with likely emails, documents, redaction, and privilege review.",
        "discovery_pain_summary": "Likely review of emails, documents, redaction, and privilege.",
        "why_now": "New complaint filed.",
        "published_at": datetime.now(timezone.utc) - timedelta(days=30),
    })
    expected = scored["confidence_score"]*.2 + scored["source_quality_score"]*.2 + scored["discovery_pain_score"]*.25 + scored["dcover_fit_score"]*.25 + scored["sales_actionability_score"]*.1
    assert scored["final_trigger_score"] == round(expected, 1)
    assert "privilege" in scored["email_body"].lower()
    assert "redaction" in scored["email_body"].lower()

def test_zero_actionability_gets_deterministic_fallback():
    scored = score_signal_payload({
        "title": "Acme data breach lawsuit filed",
        "source_url": "https://www.reuters.com/legal/acme-data-breach",
        "publisher": "Reuters",
        "parties": ["Acme"],
        "summary": "A data breach lawsuit was filed against Acme.",
        "discovery_pain_summary": "Likely discovery burden across customer notices, internal emails, security records, and incident response documents.",
        "why_now": "The lawsuit was recently filed.",
        "sales_actionability_score": 0,
    })
    assert scored["sales_actionability_score"] >= 20

def test_quality_gate_passes_only_high_quality_signal():
    db = session()
    signal = models.DiscoveredSignal(title="A v. B lawsuit filed", source_url="https://www.sec.gov/x", parties=["A", "B"], is_litigation_trigger=True, confidence_score=80, source_quality_score=90, discovery_pain_score=82, dcover_fit_score=82, sales_actionability_score=80, final_trigger_score=82, discovery_pain_summary="Likely privilege review and production burden.", why_decoverai="DecoverAI can help classify documents, identify responsive materials, accelerate privilege review, support redaction, create privilege logs, and prepare defensible production with audit trails.", published_at=datetime.now(timezone.utc) - timedelta(days=30), signal_date=datetime.now(timezone.utc) - timedelta(days=30), signal_age_days=30, freshness_status="fresh")
    db.add(signal); db.flush()
    passed, _ = quality_gate(signal, db)
    assert passed
    weak = models.DiscoveredSignal(title="Unclear", source_url="https://blog.example/unclear", parties=["A"], confidence_score=50, source_quality_score=50, discovery_pain_score=50, dcover_fit_score=50, sales_actionability_score=50, final_trigger_score=50)
    assert not quality_gate(weak, db)[0]

def test_signal_without_source_or_clear_parties_fails_gate():
    db = session()
    no_source = models.DiscoveredSignal(title="A v. B", source_url="", parties=["A", "B"], confidence_score=90, source_quality_score=90, discovery_pain_score=90, dcover_fit_score=90, sales_actionability_score=90, final_trigger_score=90)
    unclear = models.DiscoveredSignal(title="Investigation", source_url="https://www.sec.gov/x", parties=["A"], confidence_score=90, source_quality_score=90, discovery_pain_score=90, dcover_fit_score=90, sales_actionability_score=90, final_trigger_score=90)
    assert not quality_gate(no_source, db)[0]
    assert not quality_gate(unclear, db)[0]

def test_duplicate_signal_cannot_create_duplicate_opportunity():
    db = session()
    db.add(models.ScoringConfig(name="Default", is_active=True))
    opp = models.Opportunity(case_name="Acme v. Globex", normalized_key="acme-v-globex", trigger_type="data_breach")
    db.add(opp); db.flush()
    signal = models.DiscoveredSignal(title="Acme v. Globex", source_url="https://www.sec.gov/x", parties=["Acme", "Globex"], duplicate_of_opportunity_id=opp.id, confidence_score=90, source_quality_score=90, discovery_pain_score=90, dcover_fit_score=90, sales_actionability_score=90, final_trigger_score=90)
    db.add(signal); db.flush()
    existing = convert_signal_to_opportunity(db, signal)
    assert existing.id == opp.id
    assert db.query(models.Opportunity).count() == 1

def test_daily_triggers_endpoint_filters_and_sorts():
    db = session()
    db.add_all([
        models.DiscoveredSignal(title="Low", source_url="https://www.sec.gov/low", parties=["A","B"], status="new", gate_passed=False, final_trigger_score=99, confidence_score=50, source_quality_score=90, discovery_pain_score=90, dcover_fit_score=90, sales_actionability_score=90),
        models.DiscoveredSignal(title="High 1", source_url="https://www.sec.gov/one", source_domain="sec.gov", parties=["A","B"], status="new", gate_passed=True, freshness_status="fresh", signal_age_days=20, final_trigger_score=88, confidence_score=88, source_quality_score=90, discovery_pain_score=88, dcover_fit_score=88, sales_actionability_score=88),
        models.DiscoveredSignal(title="High 2", source_url="https://www.sec.gov/two", source_domain="sec.gov", parties=["C","D"], status="new", gate_passed=True, freshness_status="fresh", signal_age_days=10, final_trigger_score=92, confidence_score=90, source_quality_score=90, discovery_pain_score=90, dcover_fit_score=90, sales_actionability_score=90),
    ])
    db.commit()
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        response = client.get("/api/daily-triggers")
        assert response.status_code == 200
        data = response.json()
        assert data["page_size"] == 50
        assert [x["title"] for x in data["items"]] == ["High 2", "High 1"]
    finally:
        app.dependency_overrides.clear()

def test_robots_checker_mocked(monkeypatch):
    class Parser:
        def can_fetch(self, user_agent, url):
            return "allowed" in url
    monkeypatch.setattr(robots, "_robot_parser", lambda scheme, netloc, user_agent: Parser())
    assert robots.check_robots_allowed("https://example.com/allowed", "bot")
    assert not robots.check_robots_allowed("https://example.com/blocked", "bot")

def test_web_discovery_api_validation():
    client = TestClient(app)
    response = client.post("/api/web-discovery/runs", json={"trigger_type": "bad", "time_range": "week"})
    assert response.status_code == 422

def test_safe_score_handles_none_nan_string_float():
    assert safe_score(None) == 0
    assert safe_score(float("nan")) == 0
    assert safe_score("82.4") == 82
    assert safe_score(82.6) == 83
    assert safe_score(500) == 100
    assert safe_score(-5) == 0

def test_missing_score_during_gate_comparison_does_not_crash():
    db = session()
    signal = models.DiscoveredSignal(title="A v. B lawsuit", source_url="https://www.sec.gov/x", parties=["A", "B"], is_litigation_trigger=True, confidence_score=None)
    passed, reason = quality_gate(signal, db)
    assert not passed
    assert "confidence_score" in reason

def test_irrelevant_sec_policy_article_fails_data_breach_gate():
    db = session()
    payload = score_signal_payload({
        "title": "SEC publishes cybersecurity policy statement and guidance",
        "source_url": "https://www.sec.gov/news/policy",
        "publisher": "SEC",
        "trigger_category": "data_breach",
        "summary": "The SEC published a policy statement with general cybersecurity guidance only.",
        "parties": [],
    })
    signal = models.DiscoveredSignal(**{k: v for k, v in payload.items() if hasattr(models.DiscoveredSignal, k)}, title="SEC publishes cybersecurity policy statement and guidance", source_url="https://www.sec.gov/news/policy", parties=[])
    apply_quality_to_signal(signal, db)
    assert not signal.is_litigation_trigger
    assert not signal.gate_passed
    assert "not_litigation_trigger" in signal.gate_failure_reasons

def test_sec_policy_page_fails_regulator_actionability_with_specific_reason():
    db = session()
    payload = score_signal_payload({
        "title": "SEC Rescinds Policy Regarding Denials of Settlements in Enforcement Actions",
        "source_url": "https://www.sec.gov/newsroom/press-releases/sec-rescinds-policy-regarding-denials-settlements-enforcement-actions",
        "publisher": "SEC",
        "summary": "The SEC announced a policy change regarding denials of settlements in enforcement actions.",
        "parties": [],
        "published_at": datetime.now(timezone.utc) - timedelta(days=10),
    })
    signal = models.DiscoveredSignal(**{k: v for k, v in payload.items() if hasattr(models.DiscoveredSignal, k)}, title="SEC Rescinds Policy Regarding Denials of Settlements in Enforcement Actions", source_url="https://www.sec.gov/newsroom/press-releases/sec-rescinds-policy-regarding-denials-settlements-enforcement-actions")
    apply_quality_to_signal(signal, db)
    assert not signal.gate_passed
    assert "not_sales_actionable_regulator_item" in signal.gate_failure_reasons
    assert "no target company/person" in signal.trigger_relevance_reason

def test_sec_company_specific_enforcement_action_can_pass_when_strong():
    db = session()
    payload = score_signal_payload({
        "title": "SEC charges Acme Corp and executives with securities fraud complaint",
        "source_url": "https://www.sec.gov/news/press-release/acme-charges",
        "publisher": "SEC",
        "parties": ["SEC", "Acme Corp"],
        "summary": "The SEC filed a complaint and charges against Acme Corp after an investigation involving records, documents, and communications.",
        "discovery_pain_summary": "Government investigation likely creates records, communications, privilege review, document production, and audit trail burden.",
        "why_decoverai": "DecoverAI can help classify documents, identify responsive materials, accelerate privilege review, support redaction, create privilege logs, and prepare defensible production with audit trails.",
        "why_now": "Complaint and charges were announced recently.",
        "published_at": datetime.now(timezone.utc) - timedelta(days=20),
    })
    signal = models.DiscoveredSignal(**{k: v for k, v in payload.items() if hasattr(models.DiscoveredSignal, k)}, title="SEC charges Acme Corp and executives with securities fraud complaint", source_url="https://www.sec.gov/news/press-release/acme-charges", parties=["SEC", "Acme Corp"])
    apply_quality_to_signal(signal, db)
    assert signal.source_tier == "tier_3_regulator"
    assert signal.gate_passed

def test_courtlistener_source_gets_tier_1_court_docket():
    payload = score_signal_payload({
        "title": "Acme v. Globex complaint filed",
        "source_url": "https://www.courtlistener.com/docket/123/acme-v-globex/",
        "parties": ["Acme", "Globex"],
        "summary": "Complaint filed in trade secret lawsuit involving documents and emails.",
        "published_at": datetime.now(timezone.utc) - timedelta(days=5),
    })
    assert payload["source_tier"] == "tier_1_court_docket"
    assert payload["source_quality_score"] >= 90

def test_91_day_old_signal_fails_gate():
    db = session()
    signal = models.DiscoveredSignal(title="A v. B lawsuit filed", source_url="https://www.reuters.com/legal/a-b", parties=["A", "B"], is_litigation_trigger=True, confidence_score=90, source_quality_score=90, discovery_pain_score=90, dcover_fit_score=90, sales_actionability_score=90, final_trigger_score=90, freshness_status="stale", signal_age_days=91, discovery_pain_summary="Likely privilege review and production burden.", why_decoverai="DecoverAI can help classify documents, identify responsive materials, accelerate privilege review, support redaction, create privilege logs, and prepare defensible production with audit trails.")
    passed, reason = quality_gate(signal, db)
    assert not passed
    assert "stale_signal" in reason

def test_30_day_old_signal_can_pass_gate():
    db = session()
    signal = models.DiscoveredSignal(title="A v. B lawsuit filed", source_url="https://www.reuters.com/legal/a-b", parties=["A", "B"], is_litigation_trigger=True, confidence_score=90, source_quality_score=90, discovery_pain_score=90, dcover_fit_score=90, sales_actionability_score=90, final_trigger_score=90, freshness_status="fresh", signal_age_days=30, discovery_pain_summary="Likely privilege review and production burden.", why_decoverai="DecoverAI can help classify documents, identify responsive materials, accelerate privilege review, support redaction, create privilege logs, and prepare defensible production with audit trails.")
    assert quality_gate(signal, db)[0]

def test_unknown_date_signal_follows_setting():
    db = session()
    signal = models.DiscoveredSignal(title="A v. B lawsuit filed", source_url="https://www.reuters.com/legal/a-b", parties=["A", "B"], is_litigation_trigger=True, confidence_score=90, source_quality_score=90, discovery_pain_score=90, dcover_fit_score=90, sales_actionability_score=90, final_trigger_score=90, freshness_status="unknown", discovery_pain_summary="Likely privilege review and production burden.", why_decoverai="DecoverAI can help classify documents, identify responsive materials, accelerate privilege review, support redaction, create privilege logs, and prepare defensible production with audit trails.")
    assert not quality_gate(signal, db)[0]
    cfg = active_config(db)
    cfg.allow_unknown_signal_date = True
    assert quality_gate(signal, db)[0]

def test_sales_action_plan_is_generated_for_passed_signal():
    payload = score_signal_payload({
        "title": "Customers v. Acme data breach class action complaint filed",
        "source_url": "https://www.reuters.com/legal/acme",
        "parties": ["Customers", "Acme"],
        "summary": "Complaint filed with documents, redaction, privilege, and production burden.",
        "published_at": datetime.now(timezone.utc) - timedelta(days=10),
    })
    assert payload["sales_action_plan"]["recommended_contact_titles"]
    assert "next_best_action" in payload["sales_action_plan"]

def test_source_pack_config_loads_defaults_and_disabled_pack_is_not_used():
    packs = default_source_packs()
    assert any(p["key"] == "us_court_dockets" and p["enabled"] for p in packs)
    packs[0]["enabled"] = False
    assert all(p["key"] != packs[0]["key"] for p in enabled_source_packs(packs))

def test_undated_search_results_are_allowed_for_scraping():
    result = WebSearchResult(title="Undated legal news", url="https://www.reuters.com/legal/x", domain="reuters.com")
    assert _is_recent_search_result(result, 90)

def test_daily_triggers_max_50_and_respects_max_per_source_domain():
    db = session()
    cfg = active_config(db)
    cfg.max_daily_triggers = 50
    cfg.max_per_source_domain = 4
    for i in range(20):
        db.add(models.DiscoveredSignal(title=f"Same domain {i}", source_url=f"https://www.reuters.com/legal/{i}", source_domain="reuters.com", parties=[f"A{i}", f"B{i}"], status="new", gate_passed=True, freshness_status="fresh", signal_age_days=i, final_trigger_score=95 - i, confidence_score=90, source_quality_score=90, discovery_pain_score=90, dcover_fit_score=90, sales_actionability_score=90))
    for i in range(20):
        db.add(models.DiscoveredSignal(title=f"Other domain {i}", source_url=f"https://www.law.com/{i}", source_domain=f"law{i}.com", parties=[f"C{i}", f"D{i}"], status="new", gate_passed=True, freshness_status="fresh", signal_age_days=i, final_trigger_score=80 - i, confidence_score=90, source_quality_score=90, discovery_pain_score=90, dcover_fit_score=90, sales_actionability_score=90))
    db.commit()
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        data = client.get("/api/daily-triggers").json()
        assert len(data["items"]) <= 50
        assert sum(1 for item in data["items"] if item["source_domain"] == "reuters.com") <= 4
    finally:
        app.dependency_overrides.clear()

def test_daily_triggers_show_passed_unknown_date_signals():
    db = session()
    db.add_all([
        models.DiscoveredSignal(title="Unknown date pass", source_url="https://www.reuters.com/legal/unknown", source_domain="reuters.com", parties=["Acme"], status="new", gate_passed=True, freshness_status="unknown", final_trigger_score=65, confidence_score=80, source_quality_score=80, discovery_pain_score=80, dcover_fit_score=80, sales_actionability_score=80),
        models.DiscoveredSignal(title="Stale pass", source_url="https://www.reuters.com/legal/stale", source_domain="reuters.com", parties=["Acme"], status="new", gate_passed=True, freshness_status="stale", final_trigger_score=99, confidence_score=90, source_quality_score=90, discovery_pain_score=90, dcover_fit_score=90, sales_actionability_score=90),
    ])
    db.commit()
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        data = client.get("/api/daily-triggers").json()
        titles = {item["title"] for item in data["items"]}
        assert "Unknown date pass" in titles
        assert "Stale pass" not in titles
    finally:
        app.dependency_overrides.clear()

def test_daily_triggers_export_csv_downloads_passed_rows():
    db = session()
    db.add(models.DiscoveredSignal(title="Exportable trigger", source_url="https://www.reuters.com/legal/export", source_domain="reuters.com", parties=["Acme"], status="new", gate_passed=True, freshness_status="fresh", final_trigger_score=82, confidence_score=80, source_quality_score=80, discovery_pain_score=80, dcover_fit_score=80, sales_actionability_score=80))
    db.commit()
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        res = client.get("/api/daily-triggers/export.csv")
        assert res.status_code == 200
        assert "text/csv" in res.headers["content-type"]
        assert "daily-triggers.csv" in res.headers["content-disposition"]
        assert "Exportable trigger" in res.text
    finally:
        app.dependency_overrides.clear()

def test_discovery_run_failed_tab_shows_stale_and_unknown_date_signals():
    db = session()
    run = models.WebDiscoveryRun(query="q", trigger_type="all", status="completed")
    db.add(run); db.flush()
    db.add_all([
        models.DiscoveredSignal(discovery_run_id=run.id, title="Fresh fail", source_url="https://www.reuters.com/legal/fresh", source_domain="reuters.com", gate_passed=False, freshness_status="fresh", final_trigger_score=50, status="new"),
        models.DiscoveredSignal(discovery_run_id=run.id, title="Old fail", source_url="https://www.courtlistener.com/docket/old", source_domain="courtlistener.com", gate_passed=False, freshness_status="stale", signal_age_days=900, final_trigger_score=99, status="new"),
        models.DiscoveredSignal(discovery_run_id=run.id, title="Unknown fail", source_url="https://www.courtlistener.com/docket/unknown", source_domain="courtlistener.com", gate_passed=False, freshness_status="unknown", final_trigger_score=99, status="new"),
    ])
    db.commit()
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        data = client.get(f"/api/web-discovery/runs/{run.id}/signals?tab=failed_gate").json()
        assert {item["title"] for item in data} == {"Fresh fail", "Old fail", "Unknown fail"}
    finally:
        app.dependency_overrides.clear()

def test_realistic_class_action_signal_passes_gate():
    db = session()
    payload = score_signal_payload({
        "title": "Customers v. Acme data breach class action complaint filed",
        "source_url": "https://www.reuters.com/legal/acme-data-breach-class-action",
        "publisher": "Reuters",
        "parties": ["Customers", "Acme"],
        "matter_type": "Data Breach Class Action",
        "trigger_category": "data_breach",
        "summary": "A data breach class action complaint was filed against Acme.",
        "discovery_pain_summary": "This likely creates review, redaction, privilege, and production burden across customer notices, internal communications, security records, and incident documents.",
        "why_decoverai": "DecoverAI can help classify documents, identify responsive materials, accelerate privilege review, support redaction, create privilege logs, and prepare defensible production with audit trails.",
        "why_now": "The complaint was filed recently.",
        "published_at": datetime.now(timezone.utc) - timedelta(days=30),
    })
    signal = models.DiscoveredSignal(**{k: v for k, v in payload.items() if hasattr(models.DiscoveredSignal, k)}, title="Customers v. Acme data breach class action complaint filed", source_url="https://www.reuters.com/legal/acme-data-breach-class-action", parties=["Customers", "Acme"])
    apply_quality_to_signal(signal, db)
    assert signal.gate_passed

def test_generic_decoverai_fit_fails_gate():
    db = session()
    signal = models.DiscoveredSignal(title="A v. B lawsuit filed", source_url="https://www.sec.gov/x", parties=["A", "B"], is_litigation_trigger=True, confidence_score=90, source_quality_score=90, discovery_pain_score=90, dcover_fit_score=50, sales_actionability_score=90, final_trigger_score=90, freshness_status="fresh", signal_age_days=10, discovery_pain_summary="Privilege review and production burden likely.", why_decoverai="DecoverAI can help with legal documents.")
    passed, reason = quality_gate(signal, db)
    assert not passed
    assert "dcover_fit_score below 60" in reason

def test_settings_endpoint_defaults_and_update():
    db = session()
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        res = client.get("/api/settings")
        assert res.status_code == 200
        assert res.json()["final_trigger_score_min"] == 70
        assert res.json()["max_daily_triggers"] == 50
        assert res.json()["default_max_results"] == 40
        payload = res.json()
        payload["final_trigger_score_min"] = 80
        payload["max_signal_age_days"] = 60
        payload["default_max_results"] = 55
        put = client.put("/api/settings", json=payload)
        assert put.status_code == 200
        assert put.json()["final_trigger_score_min"] == 80
        assert put.json()["max_signal_age_days"] == 60
        assert put.json()["default_max_results"] == 55
    finally:
        app.dependency_overrides.clear()

def test_discovery_run_does_not_fail_on_missing_scores(monkeypatch):
    db = session()
    class Provider:
        def search(self, *args, **kwargs):
            from app.services.web_search.base import WebSearchResult
            return [WebSearchResult(title="Acme v. Globex lawsuit filed", url="https://www.reuters.com/legal/acme", domain="reuters.com", snippet="Complaint filed in data breach class action involving Acme and Globex.", published_at=datetime.now(timezone.utc) - timedelta(days=5))]
    monkeypatch.setattr("app.services.web_discovery.runner._search_provider", lambda: Provider())
    monkeypatch.setattr("app.services.web_discovery.runner._scrapers", lambda: [])
    monkeypatch.setattr("app.services.web_discovery.extractor.settings.openai_api_key", None)
    run = run_discovery(db, "data_breach", max_results=1, dry_run=True)
    assert run.status == "completed"
    signal = db.query(models.DiscoveredSignal).first()
    assert signal.final_trigger_score is not None

def test_discovery_run_persists_extracted_published_date(monkeypatch):
    db = session()
    class Provider:
        def search(self, *args, **kwargs):
            return [WebSearchResult(title="Acme lawsuit filed", url="https://www.reuters.com/legal/acme", domain="reuters.com", snippet="Lawsuit filed against Acme.")]
    monkeypatch.setattr("app.services.web_discovery.runner._search_provider", lambda: Provider())
    monkeypatch.setattr("app.services.web_discovery.runner._scrapers", lambda: [])
    def fake_extract(*args, **kwargs):
        return score_signal_payload({
            "title": "Acme lawsuit filed",
            "source_url": "https://www.reuters.com/legal/acme",
            "publisher": "Reuters",
            "published_at": "2026-05-01T00:00:00+00:00",
            "parties": ["Acme"],
            "summary": "Lawsuit filed against Acme.",
            "discovery_pain_summary": "Likely document production and privilege review.",
            "why_decoverai": "DecoverAI can help classify documents, accelerate privilege review, support redaction, and prepare defensible production.",
            "is_litigation_trigger": True,
        })
    monkeypatch.setattr("app.services.web_discovery.runner.extract_signal_from_text", fake_extract)
    run = run_discovery(db, "data_breach", max_results=1, dry_run=True)
    signal = db.query(models.DiscoveredSignal).first()
    assert run.status == "completed"
    assert signal.published_at is not None
    assert signal.signal_date is not None
    assert signal.freshness_status == "fresh"

def test_discovery_run_preserves_requested_geography(monkeypatch):
    db = session()
    captured = {}
    class Provider:
        def search(self, *args, **kwargs):
            return [WebSearchResult(title="Acme lawsuit filed", url="https://www.reuters.com/legal/acme-uk", domain="reuters.com", snippet="Lawsuit filed against Acme.")]
    monkeypatch.setattr("app.services.web_discovery.runner._search_provider", lambda: Provider())
    monkeypatch.setattr("app.services.web_discovery.runner._scrapers", lambda: [])
    def fake_extract(text, metadata):
        captured["geography"] = metadata["geography"]
        return score_signal_payload({
            "title": "Acme lawsuit filed",
            "source_url": "https://www.reuters.com/legal/acme-uk",
            "publisher": "Reuters",
            "parties": ["Acme"],
            "summary": "Lawsuit filed against Acme.",
            "discovery_pain_summary": "Likely document production and privilege review.",
            "why_decoverai": "DecoverAI can help classify documents, accelerate privilege review, support redaction, and prepare defensible production.",
            "is_litigation_trigger": True,
        })
    monkeypatch.setattr("app.services.web_discovery.runner.extract_signal_from_text", fake_extract)
    run = run_discovery(db, "data_breach", geography="UK", max_results=1, dry_run=True)
    assert run.geography == "UK"
    assert captured["geography"] == "UK"
