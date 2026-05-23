from __future__ import annotations
import httpx
from ...config import settings
from .base import ScrapeResult, ScraperProvider

class FirecrawlScraperProvider(ScraperProvider):
    provider_name = "firecrawl"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.firecrawl_api_key

    def scrape(self, url: str) -> ScrapeResult:
        if not self.api_key:
            raise RuntimeError("FIRECRAWL_API_KEY is not configured")
        body = {"url": url, "formats": ["markdown"], "onlyMainContent": True, "timeout": 20000}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=25) as client:
            response = client.post("https://api.firecrawl.dev/v1/scrape", json=body, headers=headers)
            response.raise_for_status()
            payload = response.json()
        data = payload.get("data") or payload
        metadata = data.get("metadata") or {}
        published_at = (
            metadata.get("publishedTime")
            or metadata.get("datePublished")
            or metadata.get("article:published_time")
            or metadata.get("og:published_time")
            or metadata.get("publishDate")
        )
        markdown = data.get("markdown") or data.get("content") or ""
        if published_at:
            markdown = f"Published at: {published_at}\n\n{markdown}"
        return ScrapeResult(
            url=url,
            final_url=metadata.get("sourceURL") or url,
            title=metadata.get("title") or "",
            markdown_or_text=markdown,
            status_code=response.status_code,
            provider_name=self.provider_name,
            published_at=published_at,
        )
