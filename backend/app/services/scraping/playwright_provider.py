from __future__ import annotations
from .base import ScrapeResult, ScraperProvider

class PlaywrightScraperProvider(ScraperProvider):
    provider_name = "playwright"

    def scrape(self, url: str) -> ScrapeResult:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError("Playwright is optional. Install playwright and browsers to enable this provider.") from exc
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.route("**/*", lambda route: route.abort() if route.request.resource_type in {"image", "media", "font"} else route.continue_())
            response = page.goto(url, timeout=15000, wait_until="domcontentloaded")
            title = page.title()
            text = page.locator("body").inner_text(timeout=5000)[:30000]
            final_url = page.url
            status = response.status if response else None
            browser.close()
        return ScrapeResult(url=url, final_url=final_url, title=title, markdown_or_text=text, status_code=status, provider_name=self.provider_name)
