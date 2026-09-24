"""Robots.txt evaluation and politeness enforcement."""

import time
import random
from urllib.parse import urlparse
import urllib.robotparser
import httpx
from caf_common.logging import get_logger

logger = get_logger("acquire.robots")


class PolitenessManager:
    def __init__(
        self,
        user_agent: str,
        min_delay_s: float = 5.0,
        max_delay_s: float = 10.0,
    ) -> None:
        self.user_agent = user_agent
        self.min_delay_s = min_delay_s
        self.max_delay_s = max_delay_s
        self._parsers: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_request_time: dict[str, float] = {}

    def get_host(self, url: str) -> str:
        return urlparse(url).netloc

    def is_allowed(self, url: str) -> bool:
        host = self.get_host(url)
        if host not in self._parsers:
            rp = urllib.robotparser.RobotFileParser()
            scheme = urlparse(url).scheme or "https"
            robots_url = f"{scheme}://{host}/robots.txt"
            try:
                resp = httpx.get(robots_url, timeout=5.0, headers={"User-Agent": self.user_agent})
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    rp.allow_all = True
            except Exception as exc:
                logger.warning("robots_fetch_failed", host=host, error=str(exc))
                rp.allow_all = True
            self._parsers[host] = rp

        return self._parsers[host].can_fetch(self.user_agent, url)

    def sleep_before_request(self, url: str) -> None:
        host = self.get_host(url)
        last_time = self._last_request_time.get(host, 0.0)
        delay = random.uniform(self.min_delay_s, self.max_delay_s)
        elapsed = time.time() - last_time
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time[host] = time.time()
