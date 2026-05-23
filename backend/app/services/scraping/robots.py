from __future__ import annotations
from functools import lru_cache
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import httpx
from ...config import settings

@lru_cache(maxsize=512)
def _robot_parser(scheme: str, netloc: str, user_agent: str) -> RobotFileParser | None:
    robots_url = f"{scheme}://{netloc}/robots.txt"
    try:
        with httpx.Client(timeout=8, headers={"User-Agent": user_agent}) as client:
            response = client.get(robots_url)
        if response.status_code >= 400:
            return None
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        return parser
    except Exception:
        return None

def check_robots_allowed(url: str, user_agent: str | None = None) -> bool:
    user_agent = user_agent or settings.scraping_user_agent
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    parser = _robot_parser(parsed.scheme, parsed.netloc, user_agent)
    if parser is None:
        return False
    try:
        return bool(parser.can_fetch(user_agent, url))
    except Exception:
        return False
