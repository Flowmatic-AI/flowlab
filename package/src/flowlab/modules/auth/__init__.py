from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from flowlab._module import Module
from flowlab.modules.auth._commands import auth_commands
from flowlab.modules.auth._dependencies import Auth, SessionAuth, get_session_user, get_user
from flowlab.modules.auth._mcp import ApiKeyVerifier, CurrentMCPUser, auth_server, current_user, get_mcp_user
from flowlab.modules.auth._models import ApiKey, BaseUser, User, fillable_fields, user_model
from flowlab.modules.auth._routers import api_keys_router, auth_router
from flowlab.modules.auth._schema import check_schema
from flowlab.modules.auth._security import (
    ACCESS_TOKEN_TYPE,
    TokenExpired,
    TokenInvalid,
    decode_token,
    get_auth_settings,
    mint_token,
)

if TYPE_CHECKING:
    from flowlab._flowlab import FlowLab

__all__ = [
    "ACCESS_TOKEN_TYPE",
    "ApiKey",
    "ApiKeyVerifier",
    "Auth",
    "BaseUser",
    "CurrentMCPUser",
    "SessionAuth",
    "TokenExpired",
    "TokenInvalid",
    "User",
    "current_user",
    "decode_token",
    "get_auth_settings",
    "get_mcp_user",
    "get_session_user",
    "get_user",
    "mint_token",
    "module",
    "user_model",
]

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _require_auth_settings(app: FlowLab) -> None:
    _ = app.auth


def module(model: type[BaseUser] = User, registration: bool = True) -> Module:
    fillable_fields(model)

    return Module(
        name="auth",
        routers=[auth_router(model, registration), api_keys_router, auth_server(model), auth_commands(model)],
        migrations=MIGRATIONS_DIR,
        mcp_auth=ApiKeyVerifier,
        setup=_require_auth_settings,
        check=check_schema,
    )
