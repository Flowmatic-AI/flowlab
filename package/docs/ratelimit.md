# Rate limiting

Fixed-window rate limits for routes and MCP tools, counted in the app's cache.

```python
from flowlab import APIRouter, MCPRouter
from flowlab.modules.ratelimit import MCPRateLimit, RateLimit

router = APIRouter()


@router.post("/contact", dependencies=[RateLimit("5/minute")])
def contact() -> None: ...


mcp = MCPRouter("app")


@mcp.tool
def search(q: str, _: None = MCPRateLimit("30/minute")) -> list[str]: ...
```

There is nothing to set up: the counters live in whatever `CACHE_DRIVER` the app uses. The default `memory` cache
counts per process. With several workers or servers, use `redis`, `valkey`, `memcached` or `database` so they share one
count.

## Limits

A limit is `"<attempts>/<unit>"` or `"<attempts>/<n> <units>"`: `"5/minute"`, `"100/hour"`, `"10/5 minutes"`,
`"1000/day"`. The units are `second`, `minute`, `hour` and `day`, singular or plural. An invalid limit raises
`ValueError` when the route or tool is defined, not on the first request.

Windows are fixed: a `"5/minute"` counter starts over at the top of every minute (every window starts at a multiple of
its length since the Unix epoch). So a client can make up to 10 calls in the two seconds around a minute boundary. That
trade-off keeps each check to one atomic cache operation on every cache driver.

## Routes

`RateLimit(limit, *, by="ip", name=None)` is a dependency. Put it in `dependencies=[...]` on a route, a router or
`include_router`.

- `by="ip"` counts per client address. Behind a proxy or load balancer, start uvicorn with `--forwarded-allow-ips` so
  the address is the client's, not the proxy's.
- `by="user"` counts per authenticated user and makes the route require auth (it uses the `Auth` dependency, so it
  needs the auth module).
- `by=` a function of the `Request` returning a string counts per whatever it returns, like a tenant header.
- Each route has its own count, keyed by method and path template (`GET /items/{item_id}` counts once for every item).
  Routes that pass the same `name` share a count.

Over the limit, the route answers 429 with `Retry-After`. Every response under the limit carries
`X-RateLimit-Limit` and `X-RateLimit-Remaining`.

## MCP tools

`MCPRateLimit(limit, *, by="key", name=None)` is a parameter default, like `CurrentMCPUser()` (FastMCP only injects
dependencies declared that way). The parameter is filled in by the server and left out of the tool's input schema.

- `by="key"` counts per API key, `by="user"` across all of a user's keys, and `by=` a function of the FastMCP
  `AccessToken` counts per whatever it returns. Without the auth module, calls count per client address.
- Each tool has its own count, keyed by its name, unless tools share a `name`.

Over the limit, the call fails with a tool error: "Too many requests. Retry in N seconds."

## Auth

The auth module limits `POST /auth/login` and `POST /auth/register` out of the box, with `AUTH_RATE_LIMIT`
(default `5/minute`; `none` turns it off):

- login counts per client address plus email (case-insensitive), as Laravel does: an attacker can't lock a user out
  from everywhere, and a successful login starts that count over;
- register counts per client address.

## When the cache is down

The limiter **fails open**: if the cache cannot be reached, the attempt is allowed and the error is logged on the
`flowlab.ratelimit` logger, so a dead cache does not take login — or any limited route — down with it. For a limit
that must hold even then, build a `RateLimiter(fail_open=False)` and use it by hand (below); it raises instead.

## Counting by hand

`limiter` (a `RateLimiter` on the app's cache) counts attempts anywhere, such as in a command or a job:

```python
from flowlab.modules.ratelimit import limiter, too_many_requests

attempt = limiter.hit("exports", f"user:{user.id}", "3/hour")

if not attempt.allowed:
    raise too_many_requests(attempt)  # a 429 HTTPException; or check attempt.retry_after yourself
```

`hit(name, identity, limit)` counts one attempt and returns an `Attempt` with `allowed`, `remaining`, `retry_after`
(seconds until the window ends) and `headers()`. `clear(name, identity, limit)` forgets the current window's
attempts. `RateLimiter(cache)` counts in a cache of your own.

Identities are hashed before they become cache keys, so emails, addresses and API keys are never stored as-is.

## Public API

`RateLimit`, `MCPRateLimit`, `Limit`, `RateLimiter`, `limiter`, `Attempt`, `client_ip`, `too_many_requests`.
