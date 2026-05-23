from __future__ import annotations
from datetime import datetime
from urllib.parse import urlparse
import feedparser
from ...config import settings
from .base import WebSearchProvider, WebSearchResult

FEEDS = [
    ("DOJ Antitrust", "https://www.justice.gov/atr/press-room.xml"),
    ("SEC Litigation Releases", "https://www.sec.gov/news/pressreleases.rss"),
    ("FTC News", "https://www.ftc.gov/feeds/press-release.xml"),
    ("CourtListener Opinions", "https://www.courtlistener.com/feed/search/?q=antitrust%20OR%20patent%20OR%20%22data%20breach%22%20OR%20securities"),
]

DEMO_RESULTS = [
    {
        "title": "Technology company faces new antitrust lawsuit over platform data practices",
        "url": "https://example.com/legal/technology-antitrust-lawsuit",
        "snippet": "A newly filed antitrust complaint alleges exclusionary conduct and requests discovery into internal emails, contracts, pricing, and customer communications.",
    },
    {
        "title": "AI startup sued for alleged trade secret misappropriation",
        "url": "https://example.com/legal/ai-trade-secret-lawsuit",
        "snippet": "The suit alleges former employees moved confidential technical documents and source materials before joining a competitor.",
    },
    {
        "title": "Public company discloses securities class action after cyber incident",
        "url": "https://example.com/legal/securities-data-breach-class-action",
        "snippet": "Shareholders allege the company understated cybersecurity risk after a data breach and regulatory inquiry.",
    },
]

def _domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")

class FallbackSearchProvider(WebSearchProvider):
    provider_name = "fallback"

    def search(self, query: str, max_results: int, time_range: str = "week", include_domains=None, exclude_domains=None):
        terms = [t.lower() for t in query.replace('"', "").split() if len(t) > 3]
        results: list[WebSearchResult] = []
        for publisher, feed_url in FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[: max_results * 2]:
                    title = getattr(entry, "title", "") or ""
                    url = getattr(entry, "link", "") or ""
                    snippet = getattr(entry, "summary", "") or title
                    haystack = f"{title} {snippet}".lower()
                    if terms and not any(term in haystack for term in terms):
                        continue
                    if include_domains and _domain(url) not in include_domains:
                        continue
                    if exclude_domains and _domain(url) in exclude_domains:
                        continue
                    published_at = None
                    if getattr(entry, "published_parsed", None):
                        published_at = datetime(*entry.published_parsed[:6])
                    results.append(WebSearchResult(title=title[:500], url=url, domain=_domain(url), snippet=snippet, published_at=published_at, score=0.6, publisher=publisher))
                    if len(results) >= max_results:
                        return results
            except Exception:
                continue
        if results:
            return results[:max_results]
        if not settings.enable_demo_data:
            return []
        return [
            WebSearchResult(title=row["title"], url=row["url"], domain=_domain(row["url"]), snippet=row["snippet"], score=0.5, publisher="Demo source")
            for row in DEMO_RESULTS[:max_results]
        ]
