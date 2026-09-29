from collections.abc import Callable
from typing import Any, Literal

from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AccessToken
from fastmcp.server.dependencies import get_access_token, get_context, get_http_request

from flowlab.modules.ratelimit._limiter import limiter
from flowlab.modules.ratelimit._limits import Limit

MCPBy = Literal["key", "user"] | Callable[[AccessToken], str]


def _tool_name() -> str:
    try:
        # FastMCP reads the call's params the same way; there is no public accessor for the tool name yet.
        params = get_context().request_context._srctx.params  # type: ignore[union-attr]
    except (AttributeError, RuntimeError):
        return "mcp"

    return f"tool {params.get('name', 'mcp')}" if isinstance(params, dict) else "mcp"


def _anonymous() -> str:
    try:
        request = get_http_request()
    except RuntimeError:
        return "anonymous"

    return f"ip:{request.client.host}" if request.client is not None else "anonymous"


def _identity(by: MCPBy) -> str:
    token = get_access_token()

    if token is None:
        return _anonymous()

    if by == "key":
        return f"key:{token.token}"

    if by == "user":
        return f"user:{token.client_id}"

    return by(token)


def MCPRateLimit(limit: str | Limit, *, by: MCPBy = "key", name: str | None = None) -> Any:
    """Limit an MCP tool: ``def tool(q: str, _: None = MCPRateLimit("30/minute"))``.

    ``by`` picks whose calls are counted: ``"key"`` (the API key, the default), ``"user"`` (every key of the user)
    or a function of the access token; unauthenticated calls count per IP. Tools each get their own count unless
    they share a ``name``. Over the limit is a tool error. The parameter is left out of the tool's input schema.
    """
    parsed = Limit.parse(limit)

    def check() -> None:
        attempt = limiter.hit(name or _tool_name(), _identity(by), parsed)

        if not attempt.allowed:
            raise ToolError(f"Too many requests. Retry in {attempt.retry_after} seconds.")

    return Depends(check)
