from __future__ import annotations
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from ...config import settings
from .base import ScrapeResult, ScraperProvider
from .robots import check_robots_allowed

MAX_BYTES = 1_500_000

class RawHttpScraperProvider(ScraperProvider):
    provider_name = "raw_http"

    def scrape(self, url: str) -> ScrapeResult:
        if not check_robots_allowed(url, settings.scraping_user_agent):
            raise PermissionError("robots.txt does not allow direct scraping or could not be checked")
        headers = {"User-Agent": settings.scraping_user_agent, "Accept": "text/html,application/xhtml+xml"}
        with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            raise ValueError(f"Unsupported content type: {content_type}")
        raw = response.content[:MAX_BYTES]
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
            tag.decompose()
        title = " ".join((soup.title.string if soup.title and soup.title.string else "").split())
        chunks = []
        for tag in soup.find_all(["h1", "h2", "p", "li", "article", "main"]):
            text = " ".join(tag.get_text(" ", strip=True).split())
            if len(text) >= 40 and text not in chunks:
                chunks.append(text)
            if sum(len(c) for c in chunks) > 30000:
                break
        text = "\n\n".join(chunks) or " ".join(soup.get_text(" ", strip=True).split())[:30000]
        return ScrapeResult(url=url, final_url=str(response.url), title=title, markdown_or_text=text, status_code=response.status_code, provider_name=self.provider_name)
