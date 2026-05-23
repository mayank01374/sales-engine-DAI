from __future__ import annotations
import time
from collections import defaultdict
from urllib.parse import urlparse
from ..config import settings

class DomainRateLimiter:
    def __init__(self, delay_seconds: float | None = None):
        self.delay_seconds = settings.web_discovery_rate_limit_seconds if delay_seconds is None else delay_seconds
        self.last_seen = defaultdict(float)

    def wait(self, url: str):
        domain = urlparse(url).netloc
        now = time.monotonic()
        elapsed = now - self.last_seen[domain]
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)
        self.last_seen[domain] = time.monotonic()
