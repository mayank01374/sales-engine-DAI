from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ScrapeResult:
    url: str
    final_url: str
    title: str
    markdown_or_text: str
    status_code: int | None
    provider_name: str
    published_at: datetime | str | None = None

class ScraperProvider:
    provider_name = "base"

    def scrape(self, url: str) -> ScrapeResult:
        raise NotImplementedError
