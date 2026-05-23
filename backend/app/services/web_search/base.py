from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass
class WebSearchResult:
    title: str
    url: str
    domain: str
    snippet: str = ""
    published_at: datetime | None = None
    score: float = 0
    publisher: str = ""

class WebSearchProvider:
    provider_name = "base"

    def search(
        self,
        query: str,
        max_results: int,
        time_range: str = "week",
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[WebSearchResult]:
        raise NotImplementedError
