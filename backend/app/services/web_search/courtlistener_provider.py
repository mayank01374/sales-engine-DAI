from __future__ import annotations
from urllib.parse import urlparse
import re
import httpx
from dateutil import parser as date_parser
from ...config import settings
from .base import WebSearchProvider, WebSearchResult

def _domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")

def _clean_html(value: str | None) -> str:
    return re.sub(r"<[^>]+>", "", value or "").strip()

def _courtlistener_url(row: dict) -> str:
    docs = row.get("recap_documents") or []
    complaint = next((doc for doc in docs if "complaint" in " ".join([doc.get("description") or "", doc.get("short_description") or ""]).lower() and doc.get("absolute_url")), None)
    available = next((doc for doc in docs if doc.get("is_available") and doc.get("absolute_url")), None)
    any_doc = next((doc for doc in docs if doc.get("absolute_url")), None)
    absolute_url = (complaint or available or any_doc or {}).get("absolute_url") or row.get("docket_absolute_url") or row.get("absolute_url") or ""
    if absolute_url.startswith("/"):
        return "https://www.courtlistener.com" + absolute_url
    return absolute_url or ""

def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return date_parser.parse(value)
    except Exception:
        return None

def _courtlistener_date(row: dict):
    dates = []
    for key in ["dateFiled", "date_filed", "dateArgued"]:
        parsed = _parse_date(row.get(key))
        if parsed:
            dates.append(parsed)
    for doc in row.get("recap_documents") or []:
        for key in ["entry_date_filed", "dateFiled", "date_filed"]:
            parsed = _parse_date(doc.get(key))
            if parsed:
                dates.append(parsed)
    if not dates:
        return None
    return max(dates)

class CourtListenerSearchProvider(WebSearchProvider):
    provider_name = "courtlistener"

    def search(self, query: str, max_results: int, time_range: str = "week", include_domains=None, exclude_domains=None):
        params = {
            "q": query,
            "type": "r",
            "order_by": "score desc",
            "page_size": max(1, min(max_results, 25)),
        }
        headers = {"User-Agent": "D-CoverAI-SignalBot/1.0"}
        if settings.courtlistener_api_key:
            headers["Authorization"] = f"Token {settings.courtlistener_api_key}"
        try:
            with httpx.Client(timeout=12, headers=headers) as client:
                response = client.get("https://www.courtlistener.com/api/rest/v4/search/", params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return []
        results = []
        for row in payload.get("results", [])[:max_results]:
            url = _courtlistener_url(row)
            if not url:
                continue
            domain = _domain(url)
            if include_domains and domain not in include_domains:
                continue
            if exclude_domains and domain in exclude_domains:
                continue
            title = row.get("caseName") or row.get("case_name") or row.get("caseNameFull") or row.get("docketNumber") or "CourtListener matter"
            snippet = _clean_html(row.get("snippet") or row.get("text") or "")
            results.append(WebSearchResult(
                title=title[:500],
                url=url,
                domain=domain or "courtlistener.com",
                snippet=snippet or "Matched CourtListener legal search result.",
                published_at=_courtlistener_date(row),
                score=0.92,
                publisher="CourtListener",
            ))
        return results
