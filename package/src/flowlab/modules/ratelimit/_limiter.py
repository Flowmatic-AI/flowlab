import hashlib
import logging
import math
import time
from dataclasses import dataclass

from flowlab._cache import get_cache
from flowlab.modules.cache import Cache
from flowlab.modules.ratelimit._limits import Limit

logger = logging.getLogger("flowlab.ratelimit")


@dataclass(frozen=True)
class Attempt:
    allowed: bool
    limit: Limit
    remaining: int
    retry_after: int
    """Seconds until the current window ends and the count starts over."""

    def headers(self) -> dict[str, str]:
        headers = {"X-RateLimit-Limit": str(self.limit.attempts), "X-RateLimit-Remaining": str(self.remaining)}

        if not self.allowed:
            headers["Retry-After"] = str(self.retry_after)

        return headers


class RateLimiter:
    """Fixed-window counters in the cache: one counter per name, identity and window, which expires with its window.

    Identities are hashed before they become cache keys, so an email or API key is never stored as-is.

    With ``fail_open`` (the default), an attempt is allowed when the cache cannot be reached, and the error is logged:
    a dead limiter must not take the routes it guards down with it.
    """

    def __init__(self, cache: Cache | None = None, prefix: str = "ratelimit", *, fail_open: bool = True) -> None:
        self._cache = cache
        self._prefix = prefix
        self.fail_open = fail_open

    @property
    def cache(self) -> Cache:
        return self._cache if self._cache is not None else get_cache()

    def hit(self, name: str, identity: str, limit: str | Limit) -> Attempt:
        """Count one attempt and say whether it is within ``limit``."""
        parsed = Limit.parse(limit)
        key, retry_after = self._window(name, identity, parsed)
        cache = self.cache

        try:
            count = cache.increment(key, ttl=parsed.seconds)
        except Exception:
            if not self.fail_open:
                raise

            logger.exception("Rate limit %r not checked: the cache is unavailable, so the attempt is allowed", name)
            return Attempt(allowed=True, limit=parsed, remaining=parsed.attempts, retry_after=retry_after)

        return Attempt(
            allowed=count <= parsed.attempts,
            limit=parsed,
            remaining=max(parsed.attempts - count, 0),
            retry_after=retry_after,
        )

    def clear(self, name: str, identity: str, limit: str | Limit) -> None:
        """Forget the attempts in the current window, like after a successful login."""
        key, _ = self._window(name, identity, Limit.parse(limit))
        cache = self.cache

        try:
            cache.delete(key)
        except Exception:
            if not self.fail_open:
                raise

            logger.exception("Rate limit %r not cleared: the cache is unavailable", name)

    def _window(self, name: str, identity: str, limit: Limit) -> tuple[str, int]:
        now = time.time()
        window = int(now // limit.seconds)
        digest = hashlib.sha256(identity.encode()).hexdigest()[:32]
        retry_after = max(math.ceil((window + 1) * limit.seconds - now), 1)

        return f"{self._prefix}:{name}:{digest}:{limit.seconds}:{window}", retry_after


limiter = RateLimiter()
