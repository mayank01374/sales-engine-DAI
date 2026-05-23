from __future__ import annotations
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from ... import models
from ...config import settings
from .. import active_config, create_or_update_opportunity, log_activity
from ..rate_limiter import DomainRateLimiter
from ..scraping.robots import check_robots_allowed
from ..scraping.raw_http_provider import RawHttpScraperProvider
from ..scraping.firecrawl_provider import FirecrawlScraperProvider
from ..scraping.playwright_provider import PlaywrightScraperProvider
from ..web_search.fallback_provider import FallbackSearchProvider
from ..web_search.tavily_provider import TavilySearchProvider
from ..web_search.courtlistener_provider import CourtListenerSearchProvider
from ..web_search.composite_provider import CompositeSearchProvider
from .dedupe import dedupe_signal
from .extractor import extract_signal_from_text
from .gemini_judge import apply_gemini_judgment
from .quality import apply_quality_to_signal, evaluate_freshness, quality_gate, safe_score
from .query_builder import build_discovery_queries
from .source_packs import enabled_source_packs

def _domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")

def _is_recent_search_result(result, max_age_days: int) -> bool:
    if result.published_at is None:
        return True
    freshness = evaluate_freshness({"published_at": result.published_at}, max_age_days=max_age_days)
    return freshness["freshness_status"] == "fresh"

def _search_provider():
    providers = [CourtListenerSearchProvider()]
    providers.append(TavilySearchProvider() if settings.tavily_api_key else FallbackSearchProvider())
    return CompositeSearchProvider(providers)

def _scrapers():
    providers = []
    if settings.firecrawl_api_key:
        providers.append(FirecrawlScraperProvider())
    providers.append(RawHttpScraperProvider())
    if settings.web_discovery_use_playwright:
        providers.append(PlaywrightScraperProvider())
    return providers

def _attempt(db: Session, signal_id: int, provider: str, status: str, started: float, http_status=None, robots_allowed=False, error_message=""):
    db.add(models.ScrapeAttempt(
        discovered_signal_id=signal_id,
        provider=provider,
        status=status,
        http_status=http_status,
        robots_allowed=robots_allowed,
        error_message=error_message[:2000],
        duration_ms=int((time.monotonic() - started) * 1000),
    ))

def run_discovery(
    db: Session,
    trigger_type: str = "all",
    geography: str = "US",
    industry: str = "",
    time_range: str = "week",
    max_results: int | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    dry_run: bool = False,
    existing_run_id: int | None = None,
) -> models.WebDiscoveryRun:
    trigger_type = trigger_type or "all"
    geography = "US"
    max_results = max(1, min(max_results or settings.web_discovery_max_results, 100))
    cfg = active_config(db)
    source_packs = enabled_source_packs(cfg.source_packs)
    queries = build_discovery_queries(trigger_type, geography, "", source_packs)
    run = db.get(models.WebDiscoveryRun, existing_run_id) if existing_run_id else None
    if run:
        run.status = "running"
        run.query = " | ".join(queries)
    else:
        run = models.WebDiscoveryRun(query=" | ".join(queries), trigger_type=trigger_type, geography=geography, industry="", time_range=time_range, status="running")
        db.add(run)
    db.commit(); db.refresh(run)
    seen = set()
    limiter = DomainRateLimiter()
    try:
        provider = _search_provider()
        search_results = []
        domain_counts = {}
        max_age_days = int(getattr(settings, "max_signal_age_days", 90) or 90)
        search_cap = min(max_results * 8, 200)
        per_query = max(2, search_cap // max(1, len(queries)) + 1)
        for query in queries:
            for result in provider.search(query, per_query, time_range, include_domains, exclude_domains):
                if result.url in seen:
                    continue
                if not _is_recent_search_result(result, max_age_days):
                    continue
                domain = result.domain or _domain(result.url)
                if domain_counts.get(domain, 0) >= 25:
                    continue
                seen.add(result.url)
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
                search_results.append(result)
                if len(search_results) >= search_cap:
                    break
            if len(search_results) >= search_cap:
                break
        kept = 0
        for result in search_results:
            if kept >= max_results:
                break
            signal = models.DiscoveredSignal(
                discovery_run_id=run.id,
                title=result.title or result.url,
                source_url=result.url,
                source_domain=result.domain or _domain(result.url),
                publisher=result.publisher or result.domain,
                published_at=result.published_at,
                raw_snippet=result.snippet or "",
                trigger_type=trigger_type,
                status="new",
            )
            db.add(signal); db.flush()
            try:
                scrape_text = ""
                if not dry_run and not result.url.startswith("https://example.com/"):
                    for scraper in _scrapers():
                        started = time.monotonic()
                        robots_allowed = scraper.provider_name != "raw_http" or check_robots_allowed(result.url, settings.scraping_user_agent)
                        if not robots_allowed and scraper.provider_name == "raw_http":
                            _attempt(db, signal.id, scraper.provider_name, "skipped", started, robots_allowed=False, error_message="robots.txt disallowed or unavailable")
                            continue
                        try:
                            limiter.wait(result.url)
                            scraped = scraper.scrape(result.url)
                            scrape_text = scraped.markdown_or_text or ""
                            if scraped.title and len(scraped.title) > len(signal.title):
                                signal.title = scraped.title[:500]
                            signal.scraped_text = scrape_text[:30000]
                            _attempt(db, signal.id, scraped.provider_name, "success", started, scraped.status_code, robots_allowed=True)
                            break
                        except Exception as exc:
                            _attempt(db, signal.id, scraper.provider_name, "failed", started, robots_allowed=robots_allowed, error_message=str(exc))
                metadata = {
                    "title": signal.title,
                    "snippet": signal.raw_snippet,
                    "url": signal.source_url,
                    "source_domain": signal.source_domain,
                    "publisher": signal.publisher,
                    "published_at": signal.published_at,
                    "trigger_type": trigger_type,
                    "geography": geography,
                }
                extraction = extract_signal_from_text(scrape_text or signal.raw_snippet, metadata)
                signal.title = extraction.get("title") or signal.title
                signal.trigger_type = extraction.get("trigger_type") or trigger_type
                signal.case_type = extraction.get("case_type") or extraction.get("matter_type") or ""
                signal.matter_type = extraction.get("matter_type") or signal.case_type
                signal.trigger_category = extraction.get("trigger_category") or signal.trigger_type
                signal.parties = extraction.get("parties") or []
                signal.party_roles = extraction.get("party_roles") or {}
                signal.law_firms = extraction.get("law_firms") or []
                signal.courts = extraction.get("courts") or []
                signal.regulators = extraction.get("regulators") or []
                signal.court_or_regulator = extraction.get("court_or_regulator") or ", ".join((signal.courts or signal.regulators or [])[:1])
                signal.jurisdiction = extraction.get("jurisdiction") or geography
                signal.summary = extraction.get("summary") or signal.raw_snippet
                signal.factual_basis = extraction.get("factual_basis") or signal.raw_snippet
                signal.discovery_pain_summary = extraction.get("discovery_pain_summary") or ""
                signal.why_now = extraction.get("why_now") or ""
                signal.why_decoverai = extraction.get("why_decoverai") or extraction.get("why_relevant_to_dcover") or ""
                signal.why_relevant_to_decoverAI = signal.why_decoverai
                signal.recommended_personas = extraction.get("recommended_personas") or []
                signal.sales_angle_one_liner = extraction.get("sales_angle_one_liner") or ""
                signal.email_subject = extraction.get("email_subject") or ""
                signal.email_body = extraction.get("email_body") or ""
                signal.linkedin_message = extraction.get("linkedin_message") or ""
                signal.call_opener = extraction.get("call_opener") or ""
                signal.discovery_burden_score = extraction.get("discovery_burden_score") or extraction.get("discovery_pain_score") or 0
                signal.urgency_score = extraction.get("urgency_score") or 0
                signal.decover_fit_score = extraction.get("decover_fit_score") or extraction.get("dcover_fit_score") or 0
                signal.confidence_score = extraction.get("confidence_score") or 0
                signal.source_quality_score = extraction.get("source_quality_score") or 0
                signal.discovery_pain_score = extraction.get("discovery_pain_score") or signal.discovery_burden_score
                signal.dcover_fit_score = extraction.get("dcover_fit_score") or signal.decover_fit_score
                signal.sales_actionability_score = extraction.get("sales_actionability_score") or 0
                signal.final_trigger_score = extraction.get("final_trigger_score") or 0
                signal.extraction_warnings = extraction.get("extraction_warnings") or []
                signal.missing_fields = extraction.get("missing_fields") or []
                signal.is_litigation_trigger = bool(extraction.get("is_litigation_trigger"))
                signal.trigger_relevance_reason = extraction.get("trigger_relevance_reason") or ""
                if extraction.get("rejection_reason") and not signal.is_litigation_trigger:
                    signal.rejection_reason = extraction.get("rejection_reason")
                dedupe_signal(db, signal)
                if signal.duplicate_of_opportunity_id:
                    signal.duplicate_reason = f"Matches existing opportunity #{signal.duplicate_of_opportunity_id}."
                apply_quality_to_signal(signal, db)
                if signal.freshness_status == "stale":
                    signal.status = "stale"
                    signal.gate_status = "failed"
                    signal.gate_passed = False
                    signal.gate_failure_reasons = list(dict.fromkeys((signal.gate_failure_reasons or []) + ["stale_signal"]))
                    signal.gate_reason = "; ".join(signal.gate_failure_reasons)
                    kept += 1
                    continue
                try:
                    apply_gemini_judgment(signal)
                except Exception as exc:
                    warnings = list(signal.extraction_warnings or [])
                    warnings.append(f"Gemini judgment unavailable: {exc}")
                    signal.extraction_warnings = warnings
                kept += 1
            except Exception as inner_exc:
                signal.status = "processing_failed"
                signal.gate_status = "failed"
                signal.gate_passed = False
                signal.gate_failure_reasons = list(dict.fromkeys((signal.gate_failure_reasons or []) + ["processing_failed"]))
                signal.gate_reason = f"Processing crashed: {inner_exc}"
                warnings = list(signal.extraction_warnings or [])
                warnings.append(f"Processing crashed: {inner_exc}")
                signal.extraction_warnings = warnings
                kept += 1
                db.flush()
                continue
        run.total_results = kept
        run.status = "completed"
        db.commit(); db.refresh(run)
        return run
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        db.commit(); db.refresh(run)
        return run

def convert_signal_to_opportunity(db: Session, signal: models.DiscoveredSignal) -> models.Opportunity:
    if signal.status == "converted" and signal.duplicate_of_opportunity_id:
        return db.get(models.Opportunity, signal.duplicate_of_opportunity_id)
    if signal.duplicate_of_opportunity_id:
        existing = db.get(models.Opportunity, signal.duplicate_of_opportunity_id)
        if existing:
            signal.status = "converted"
            log_activity(db, existing.id, "web_discovery_duplicate_linked", f"Linked duplicate Web Discovery signal {signal.id}", actor_name="Sales", metadata={"signal_id": signal.id, "source_url": signal.source_url})
            db.flush()
            return existing
    passed, reason = quality_gate(signal, db)
    if not passed and not settings.enable_force_convert:
        raise ValueError(f"Signal does not pass quality gate: {reason}")
    data = {
        "case_name": signal.title,
        "trigger_type": signal.trigger_type or "Web Discovery Signal",
        "case_type": signal.case_type or signal.matter_type or "Litigation",
        "matter_type": signal.matter_type or signal.case_type or "Litigation",
        "trigger_category": signal.trigger_category or signal.trigger_type,
        "parties": signal.parties or [],
        "party_roles": signal.party_roles or {},
        "law_firms": signal.law_firms or [],
        "court_or_regulator": signal.court_or_regulator,
        "jurisdiction": signal.jurisdiction,
        "summary": signal.summary or signal.raw_snippet,
        "factual_basis": signal.factual_basis,
        "discovery_pain_summary": signal.discovery_pain_summary,
        "why_now": signal.why_now,
        "why_decoverai": signal.why_decoverai or signal.why_relevant_to_decoverAI,
        "recommended_personas": signal.recommended_personas or [],
        "sales_angle_one_liner": signal.sales_angle_one_liner,
        "email_subject": signal.email_subject,
        "email_body": signal.email_body,
        "linkedin_message": signal.linkedin_message,
        "call_opener": signal.call_opener,
        "confidence_score": signal.confidence_score,
        "source_quality_score": signal.source_quality_score,
        "discovery_pain_score": signal.discovery_pain_score,
        "dcover_fit_score": signal.dcover_fit_score,
        "sales_actionability_score": signal.sales_actionability_score,
        "final_trigger_score": signal.final_trigger_score,
        "source_tier": signal.source_tier,
        "source_reason": signal.source_reason,
        "sales_action_plan": signal.sales_action_plan or {},
        "is_litigation_trigger": signal.is_litigation_trigger,
        "trigger_relevance_reason": signal.trigger_relevance_reason,
        "gate_status": signal.gate_status,
        "gate_failure_reasons": signal.gate_failure_reasons or [],
        "extraction_warnings": signal.extraction_warnings or [],
        "missing_fields": signal.missing_fields or [],
        "source_url": signal.source_url,
        "source_title": signal.title,
        "publisher": signal.publisher or signal.source_domain,
        "snippet": (signal.raw_snippet or "") + ("\n\nScraped preview:\n" + signal.scraped_text[:1500] if signal.scraped_text else ""),
        "evidence_type": "web_discovery",
        "credibility_score": signal.confidence_score or 70,
    }
    opp = create_or_update_opportunity(db, data)
    signal.status = "converted"
    signal.duplicate_of_opportunity_id = opp.id
    run = signal.discovery_run
    if run:
        run.converted_count = (run.converted_count or 0) + 1
    log_activity(db, opp.id, "web_discovery_converted", f"Converted Web Discovery signal {signal.id}", actor_name="Sales", metadata={"signal_id": signal.id, "source_url": signal.source_url})
    db.flush()
    return opp
