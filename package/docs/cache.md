# Cache

`flowlab.modules.cache` is a small cache abstraction with pluggable adapters:
Redis, Valkey, Memcached, a database table (via `flowlab.modules.db`) and an
in-process shared-memory store.

```python
from flowlab.modules.cache import Cache

cache = Cache.shared_memory()
```

## Constructors

| Constructor | Adapter | Requires |
| --- | --- | --- |
| `Cache.shared_memory()` | in-process dict | nothing |
| `Cache.connect_redis(host="localhost", port=6379, db=0, password=None, **options)` | Redis | `redis` |
| `Cache.connect_valkey(host="localhost", port=6379, db=0, password=None, **options)` | Valkey | `valkey` |
| `Cache.connect_memcached(host="localhost", port=11211, **options)` | Memcached | `pymemcache` |
| `Cache.connect_database(db, table="cache")` | table in a `flowlab.modules.db` `DB` | `flowlab.modules.db` |

Extra `**options` are passed to the underlying client. Adapters are imported
lazily, so only the client library you actually use has to be installed.
`Cache(adapter)` accepts any `AdapterABC` implementation (from `flowlab.modules.cache.adapters`) directly.

## API

```python
cache.set("key", {"any": "picklable value"}, ttl=60)  # ttl in seconds, optional
cache.get("key")  # None if missing/expired
cache.exists("key")  # bool
cache.delete("key")
cache.clear()  # remove every entry

cache.add("key", "value", ttl=60)  # set only if absent; returns bool
cache.pull("key", default=None)  # get, then delete; default if missing
cache.remember("key", lambda: expensive(), ttl=60)  # get, or compute + store
cache.increment("hits", ttl=60)  # atomic counter; returns the new value
cache.decrement("stock", 3)
cache.close()  # release the adapter connection
```

`Cache` is a context manager (`with Cache.connect_redis() as cache: ...`),
which calls `close()` on exit.

Notes:

- `get` returns `None` for a missing key, so `pull` and `remember` treat a
  stored `None` as missing.
- `add` is atomic on Redis, Valkey, Memcached and shared memory. On the database adapter it is
  an exists-then-set check and is not atomic.

## Counters

`increment(key, amount=1, ttl=None)` atomically adds to a counter and returns the new value, and `decrement` subtracts.
A missing or expired counter starts from zero. `ttl` only applies when the counter is created, so a counter made with
`ttl=60` disappears 60 seconds after its first increment, however often it is incremented after that. This is what
[rate limiting](ratelimit.md) builds on.

- Every adapter is atomic, the database one included: it does a compare-and-set, retrying when another writer got
  there first, so concurrent workers never lose a count.
- Counters are stored as plain integers, not pickles. Read one with `increment(key, 0)`, not `get`.
- Memcached counters stop at zero, and their `ttl` has whole-second granularity.

## Value serialization

Values are serialized with `pickle`. Any picklable object round-trips.
The database adapter additionally base64-encodes the pickle so it fits in a
text column. Only read caches you trust: unpickling untrusted data can execute
arbitrary code.

## Database adapter

`Cache.connect_database(db, table="cache")` creates the table if it does not
exist (`CREATE TABLE IF NOT EXISTS`), so it needs no migration. A FlowLab app with
`CACHE_DRIVER=database` does this when it opens the cache at startup:

| Column | Type | Notes |
| --- | --- | --- |
| `key` | string (VARCHAR 255), not null | primary key; a string rather than text so MySQL/MariaDB accept the key |
| `value` | text, not null | base64-encoded pickle |
| `expires_at` | float, nullable | unix timestamp; `NULL` means no expiry |

Expired rows are deleted lazily when read.

## Testing

Tests live in `tests/modules/cache/`. Redis, Valkey and Memcached tests skip
themselves when no server is reachable on localhost (ports 6379, 6380 and
11211 respectively). Database tests use an in-memory SQLite database.

```bash
.venv/bin/python -m pytest tests/modules/cache -q
```
