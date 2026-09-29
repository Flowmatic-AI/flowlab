from __future__ import annotations

from typing import Any

from flowlab.modules.cache.adapters._redis_like import RedisLikeAdapter


class RedisAdapter(RedisLikeAdapter):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        **options: Any,
    ) -> None:
        import redis

        super().__init__(redis.Redis(host=host, port=port, db=db, password=password, **options))
