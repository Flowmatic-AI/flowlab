import pytest

from flowlab.modules.cache import Cache
from flowlab.modules.ratelimit import RateLimiter, _limiter


def test_allows_up_to_the_limit_then_refuses() -> None:
    limiter = RateLimiter(Cache.shared_memory())

    attempts = [limiter.hit("login", "1.2.3.4", "3/minute") for _ in range(4)]

    assert [attempt.allowed for attempt in attempts] == [True, True, True, False]
    assert [attempt.remaining for attempt in attempts] == [2, 1, 0, 0]
    assert 1 <= attempts[-1].retry_after <= 60
    assert attempts[-1].headers() == {
        "X-RateLimit-Limit": "3",
        "X-RateLimit-Remaining": "0",
        "Retry-After": str(attempts[-1].retry_after),
    }
    assert "Retry-After" not in attempts[0].headers()


def test_names_and_identities_are_counted_separately() -> None:
    limiter = RateLimiter(Cache.shared_memory())
    limiter.hit("login", "a", "1/minute")

    assert limiter.hit("login", "a", "1/minute").allowed is False
    assert limiter.hit("login", "b", "1/minute").allowed is True
    assert limiter.hit("register", "a", "1/minute").allowed is True


def test_clear_starts_the_count_over() -> None:
    limiter = RateLimiter(Cache.shared_memory())
    limiter.hit("login", "a", "1/minute")
    limiter.clear("login", "a", "1/minute")

    assert limiter.hit("login", "a", "1/minute").allowed is True


def test_a_new_window_starts_the_count_over(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1_000_020.0]
    monkeypatch.setattr(_limiter.time, "time", lambda: now[0])
    limiter = RateLimiter(Cache.shared_memory())
    limiter.hit("login", "a", "1/minute")

    refused = limiter.hit("login", "a", "1/minute")
    now[0] += refused.retry_after

    assert refused.allowed is False
    assert refused.retry_after == 60 - 1_000_020 % 60
    assert limiter.hit("login", "a", "1/minute").allowed is True


def test_identities_are_hashed_in_cache_keys() -> None:
    cache = Cache.shared_memory()
    RateLimiter(cache).hit("login", "ada@example.com", "1/minute")

    keys = list(cache._adapter._store)  # type: ignore[attr-defined]

    assert len(keys) == 1
    assert "ada@example.com" not in keys[0]
    assert keys[0].startswith("ratelimit:login:")


class _BrokenCache:
    def increment(self, key: str, amount: int = 1, ttl: float | None = None) -> int:
        raise ConnectionError("cache is down")

    def delete(self, key: str) -> None:
        raise ConnectionError("cache is down")


def test_a_dead_cache_lets_attempts_through_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    limiter = RateLimiter(_BrokenCache())  # type: ignore[arg-type]

    attempts = [limiter.hit("login", "a", "1/minute") for _ in range(3)]
    limiter.clear("login", "a", "1/minute")

    assert all(attempt.allowed for attempt in attempts)
    assert attempts[0].remaining == 1
    assert "cache is unavailable" in caplog.text


def test_fail_closed_raises_when_the_cache_is_dead() -> None:
    limiter = RateLimiter(_BrokenCache(), fail_open=False)  # type: ignore[arg-type]

    with pytest.raises(ConnectionError):
        limiter.hit("login", "a", "1/minute")

    with pytest.raises(ConnectionError):
        limiter.clear("login", "a", "1/minute")
