from collections.abc import Callable
from typing import Any, Literal

from fastapi import Depends, HTTPException, Request, Response, status

from flowlab.modules.ratelimit._limiter import Attempt, limiter
from flowlab.modules.ratelimit._limits import Limit

By = Literal["ip", "user"] | Callable[[Request], str]


def client_ip(request: Request) -> str:
    """The client address as the server sees it. Behind a proxy, start uvicorn with ``--forwarded-allow-ips``."""
    return request.client.host if request.client is not None else "unknown"


def too_many_requests(attempt: Attempt) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Too many requests. Retry in {attempt.retry_after} seconds.",
        headers=attempt.headers(),
    )


def _route_name(request: Request) -> str:
    route = request.scope.get("route")

    return f"{request.method} {getattr(route, 'path', request.url.path)}"


def RateLimit(limit: str | Limit, *, by: By = "ip", name: str | None = None) -> Any:
    """Limit a route: ``@router.get("/", dependencies=[RateLimit("60/minute")])``.

    ``by`` picks whose attempts are counted: ``"ip"`` (the default), ``"user"`` (the authenticated user, which makes
    the route require auth) or a function of the request. Routes each get their own count unless they share a
    ``name``. Over the limit is a 429 with ``Retry-After``; every response gets ``X-RateLimit-Limit`` and
    ``X-RateLimit-Remaining``.
    """
    parsed = Limit.parse(limit)

    def check(request: Request, response: Response, identity: str) -> None:
        attempt = limiter.hit(name or _route_name(request), identity, parsed)

        if not attempt.allowed:
            raise too_many_requests(attempt)

        response.headers.update(attempt.headers())

    if by == "user":
        from flowlab.modules.auth import Auth

        def by_user(request: Request, response: Response, user: Auth) -> None:
            check(request, response, f"user:{user.id}")

        return Depends(by_user)

    identify = client_ip if by == "ip" else by

    def by_request(request: Request, response: Response) -> None:
        check(request, response, identify(request))

    return Depends(by_request)
