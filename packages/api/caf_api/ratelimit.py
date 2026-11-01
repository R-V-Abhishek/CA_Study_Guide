"""In-process token buckets. The API runs as a single worker, so process memory is the right scope."""

from dataclasses import dataclass
import re
import time
from typing import Callable

MAX_TRACKED_KEYS = 10_000


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern
    per_minute: int
    by: str  # "ip" or "session"


RULES = (
    Rule("login", re.compile(r"^/auth/login$"), 20, "ip"),
    Rule("source_pages", re.compile(
        r"^/api/v1/(questions/[^/]+/pages/|published-sources/|published-assets/)"), 120, "session"),
    Rule("search", re.compile(r"^/api/v1/search$"), 60, "session"),
)


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.buckets: dict[tuple[str, str], tuple[float, float]] = {}

    def check(self, rule: Rule, identity: str) -> float | None:
        """Take one token. Returns None when allowed, else the seconds until a token is available."""
        now = self.clock()
        rate = rule.per_minute / 60
        tokens, updated = self.buckets.get((rule.name, identity), (float(rule.per_minute), now))
        tokens = min(float(rule.per_minute), tokens + (now - updated) * rate)
        if tokens < 1:
            self.buckets[(rule.name, identity)] = (tokens, now)
            return (1 - tokens) / rate
        self.buckets[(rule.name, identity)] = (tokens - 1, now)
        if len(self.buckets) > MAX_TRACKED_KEYS:
            self.buckets = {key: value for key, value in self.buckets.items() if now - value[1] < 120}
        return None

    def match(self, path: str) -> Rule | None:
        return next((rule for rule in RULES if rule.pattern.match(path)), None)
