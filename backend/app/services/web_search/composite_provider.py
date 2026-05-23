from __future__ import annotations
from .base import WebSearchProvider, WebSearchResult

class CompositeSearchProvider(WebSearchProvider):
    provider_name = "composite"

    def __init__(self, providers: list[WebSearchProvider]):
        self.providers = providers

    def search(self, query: str, max_results: int, time_range: str = "week", include_domains=None, exclude_domains=None):
        results: list[WebSearchResult] = []
        seen = set()
        provider_batches: list[list[WebSearchResult]] = []
        for provider in self.providers:
            batch = []
            for result in provider.search(query, max_results, time_range, include_domains, exclude_domains):
                if result.url in seen:
                    continue
                seen.add(result.url)
                batch.append(result)
            provider_batches.append(batch)
        index = 0
        while len(results) < max_results and any(index < len(batch) for batch in provider_batches):
            for batch in provider_batches:
                if index < len(batch) and len(results) < max_results:
                    results.append(batch[index])
            index += 1
        return results
