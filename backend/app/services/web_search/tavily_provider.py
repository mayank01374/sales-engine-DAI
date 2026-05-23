from __future__ import annotations
from datetime import datetime
from urllib.parse import urlparse
import httpx
from ...config import settings
from .base import WebSearchProvider, WebSearchResult

def _domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")

def _date(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

class TavilySearchProvider(WebSearchProvider):
    provider_name = "tavily"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.tavily_api_key

    def search(self, query: str, max_results: int, time_range: str = "week", include_domains=None, exclude_domains=None):
        if not self.api_key:
            return []
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max(1, min(max_results, 50)),
            "search_depth": "advanced",
            "include_answer": False,
            "include_raw_content": False,
            "topic": "news",
        }
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains
        with httpx.Client(timeout=20) as client:
            response = client.post("https://api.tavily.com/search", json=payload)
            response.raise_for_status()
            data = response.json()
        results = []
        for row in data.get("results", []):
            url = row.get("url") or ""
            if not url:
                continue
            results.append(WebSearchResult(
                title=(row.get("title") or url)[:500],
                url=url,
                domain=_domain(url),
                snippet=row.get("content") or row.get("snippet") or "",
                published_at=_date(row.get("published_date")),
                score=float(row.get("score") or 0),
                publisher=_domain(url),
            ))
        return results
