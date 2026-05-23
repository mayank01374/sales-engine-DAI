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
        return ScrapeResult(
            url=url,
            final_url=metadata.get("sourceURL") or url,
            title=metadata.get("title") or "",
            markdown_or_text=data.get("markdown") or data.get("content") or "",
            status_code=response.status_code,
            provider_name=self.provider_name,
        )
