from typing import Any

from anyio.to_thread import run_sync
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_access_token

from flowlab._database import get_db
from flowlab._routing import MCPRouter
from flowlab.modules.auth import _api_keys as service
from flowlab.modules.auth._models import BaseUser, user_model
from flowlab.modules.auth._security import is_api_key
from flowlab.modules.db import DB as Database

USER_ID_CLAIM = "user_id"


class ApiKeyVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        if not is_api_key(token):
            return None

        user = await run_sync(service.user_from_api_key, get_db(), token)

        if user is None:
            return None

        return AccessToken(token=token, client_id=str(user.id), scopes=[], claims={USER_ID_CLAIM: user.id})


def current_user(db: Database) -> BaseUser:
    access_token = get_access_token()

    if access_token is None:
        raise ToolError("Not authenticated")

    user = (
        db.select_models(user_model())
        .where_equals("id", access_token.claims[USER_ID_CLAIM])
        .where_is_null("deleted_at")
        .fetch_model()
    )

    if user is None:
        raise ToolError("User no longer exists")

    return user


def get_mcp_user() -> BaseUser:
    return current_user(get_db())


def CurrentMCPUser() -> Any:
    """Inject the user who owns the calling API key: ``def tool(user: User = CurrentMCPUser())``."""
    return Depends(get_mcp_user)


def auth_server(model: type[BaseUser]) -> MCPRouter:
    server = MCPRouter("auth")

    def whoami(user: BaseUser = CurrentMCPUser()) -> BaseUser:
        return user

    whoami.__annotations__["return"] = model
    server.tool(whoami)

    return server
