from __future__ import annotations

import json
import time
from typing import Any

from flowlab.modules.queue.adapters._base import AdapterABC, FailedJob, ReservedJob

# Each queue is a list of waiting jobs plus two sorted sets scored by time: delayed jobs (when they are due) and
# reserved jobs (when their reservation runs out). Popping first moves every due job from both sets onto the list,
# so delayed jobs become available and jobs whose worker died are handed out again. Each job is an envelope,
# {"id", "payload", "attempts"}; the reserved envelope itself is the receipt.
POP_SCRIPT = """
for _, key in ipairs({KEYS[2], KEYS[3]}) do
    local due = redis.call('ZRANGEBYSCORE', key, '-inf', ARGV[1])
    for _, job in ipairs(due) do
        redis.call('ZREM', key, job)
        redis.call('RPUSH', KEYS[1], job)
    end
end
local job = redis.call('LPOP', KEYS[1])
if not job then
    return false
end
local envelope = cjson.decode(job)
envelope['attempts'] = envelope['attempts'] + 1
local reserved = cjson.encode(envelope)
redis.call('ZADD', KEYS[3], ARGV[2], reserved)
return reserved
"""

RELEASE_SCRIPT = """
if redis.call('ZREM', KEYS[1], ARGV[1]) == 1 then
    redis.call('ZADD', KEYS[2], ARGV[2], ARGV[1])
end
"""

FAIL_SCRIPT = """
if redis.call('ZREM', KEYS[1], ARGV[1]) == 1 then
    redis.call('HSET', KEYS[2], ARGV[2], ARGV[3])
    redis.call('ZADD', KEYS[3], ARGV[4], ARGV[2])
end
"""


class RedisLikeAdapter(AdapterABC):
    """Shared implementation for clients that speak the Redis wire protocol (redis-py, valkey-py)."""

    def __init__(self, client: Any, retry_after: float = 90, prefix: str = "flowlab:queue") -> None:
        self._client = client
        self._retry_after = retry_after
        self._prefix = prefix

    def push(self, queue: str, id: str, payload: str, delay: float = 0) -> None:
        envelope = json.dumps({"id": id, "payload": payload, "attempts": 0})

        if delay > 0:
            self._client.zadd(self._delayed(queue), {envelope: time.time() + delay})
        else:
            self._client.rpush(self._waiting(queue), envelope)

    def pop(self, queue: str) -> ReservedJob | None:
        now = time.time()
        keys = (self._waiting(queue), self._delayed(queue), self._reserved(queue))
        reserved = self._client.eval(POP_SCRIPT, len(keys), *keys, now, now + self._retry_after)

        if not reserved:
            return None

        receipt = reserved.decode() if isinstance(reserved, bytes) else reserved
        envelope = json.loads(receipt)

        return ReservedJob(
            id=envelope["id"],
            queue=queue,
            payload=envelope["payload"],
            attempts=int(envelope["attempts"]),
            receipt=receipt,
        )

    def delete(self, job: ReservedJob) -> None:
        self._client.zrem(self._reserved(job.queue), job.receipt)

    def release(self, job: ReservedJob, delay: float = 0) -> None:
        keys = (self._reserved(job.queue), self._delayed(job.queue))
        self._client.eval(RELEASE_SCRIPT, len(keys), *keys, job.receipt, time.time() + delay)

    def fail(self, job: ReservedJob, exception: str) -> None:
        failed_at = time.time()
        record = json.dumps(
            {"queue": job.queue, "payload": job.payload, "exception": exception, "failed_at": failed_at}
        )
        keys = (self._reserved(job.queue), self._failed, self._failed_index)
        self._client.eval(FAIL_SCRIPT, len(keys), *keys, job.receipt, job.id, record, failed_at)

    def size(self, queue: str) -> int:
        pipe = self._client.pipeline()
        pipe.llen(self._waiting(queue))
        pipe.zcard(self._delayed(queue))
        pipe.zcard(self._reserved(queue))
        return sum(int(count) for count in pipe.execute())

    def clear(self, queue: str) -> int:
        count = self.size(queue)
        self._client.delete(self._waiting(queue), self._delayed(queue), self._reserved(queue))
        return count

    def failed(self) -> list[FailedJob]:
        ids = [self._text(id) for id in self._client.zrevrange(self._failed_index, 0, -1)]

        if not ids:
            return []

        records = self._client.hmget(self._failed, ids)
        return [self._failed_job(id, record) for id, record in zip(ids, records, strict=True) if record is not None]

    def find_failed(self, id: str) -> FailedJob | None:
        record = self._client.hget(self._failed, id)
        return None if record is None else self._failed_job(id, record)

    def forget_failed(self, id: str) -> bool:
        pipe = self._client.pipeline()
        pipe.hdel(self._failed, id)
        pipe.zrem(self._failed_index, id)
        return bool(pipe.execute()[0])

    def flush_failed(self) -> int:
        count = int(self._client.hlen(self._failed))
        self._client.delete(self._failed, self._failed_index)
        return count

    def close(self) -> None:
        self._client.close()

    def _waiting(self, queue: str) -> str:
        return f"{self._prefix}:{queue}"

    def _delayed(self, queue: str) -> str:
        return f"{self._prefix}:{queue}:delayed"

    def _reserved(self, queue: str) -> str:
        return f"{self._prefix}:{queue}:reserved"

    @property
    def _failed(self) -> str:
        return f"{self._prefix}-failed"

    @property
    def _failed_index(self) -> str:
        return f"{self._prefix}-failed:index"

    @staticmethod
    def _text(value: bytes | str) -> str:
        return value.decode() if isinstance(value, bytes) else value

    def _failed_job(self, id: str, record: bytes | str) -> FailedJob:
        data = json.loads(self._text(record))
        return FailedJob(
            id=id,
            queue=data["queue"],
            payload=data["payload"],
            exception=data["exception"],
            failed_at=float(data["failed_at"]),
        )
