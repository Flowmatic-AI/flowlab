from typing import Any

from fastapi import APIRouter, Request, status

from flowlab._database import DB
from flowlab.modules.auth import _api_keys as service
from flowlab.modules.auth._dependencies import Auth, SessionAuth
from flowlab.modules.auth._email import normalize_email
from flowlab.modules.auth._models import ApiKey, BaseUser
from flowlab.modules.auth._schemas import ApiKeyCreate, Credentials, NewApiKey, Token, registration_schema
from flowlab.modules.auth._security import get_auth_settings
from flowlab.modules.auth._users import issue_token, login, register
from flowlab.modules.ratelimit import client_ip, limiter, too_many_requests


def throttle(name: str, identity: str) -> None:
    limit = get_auth_settings().auth_rate_limit

    if limit is None:
        return

    attempt = limiter.hit(name, identity, limit)

    if not attempt.allowed:
        raise too_many_requests(attempt)


def forget_attempts(name: str, identity: str) -> None:
    limit = get_auth_settings().auth_rate_limit

    if limit is not None:
        limiter.clear(name, identity, limit)


def auth_router(user_model: type[BaseUser], registration: bool = True) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])
    token = Token[user_model]  # type: ignore[valid-type]

    def register_route(request: Request, db: DB, body: Any) -> Any:
        throttle("auth:register", client_ip(request))
        user = register(db, body.email, body.password, body.attributes())

        return token(access_token=issue_token(user), user=user)

    register_route.__annotations__["body"] = registration_schema(user_model)

    def login_route(request: Request, db: DB, credentials: Credentials) -> Any:
        # Per IP and email, like Laravel: one attacker can't lock a user out from everywhere, and a successful
        # login starts the count over.
        identity = f"{client_ip(request)}|{normalize_email(credentials.email)}"
        throttle("auth:login", identity)
        user = login(db, credentials.email, credentials.password)
        forget_attempts("auth:login", identity)

        return token(access_token=issue_token(user), user=user)

    def me_route(user: Auth) -> Any:
        return user

    if registration:
        router.add_api_route(
            "/register",
            register_route,
            methods=["POST"],
            status_code=status.HTTP_201_CREATED,
            response_model=token,
            name="register",
        )

    router.add_api_route("/login", login_route, methods=["POST"], response_model=token, name="login")
    router.add_api_route("/me", me_route, methods=["GET"], response_model=user_model, name="me")

    return router


api_keys_router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@api_keys_router.post("", status_code=status.HTTP_201_CREATED)
def create_route(db: DB, user: SessionAuth, body: ApiKeyCreate) -> NewApiKey:
    api_key, token = service.create(db, user, body.name)

    return NewApiKey(api_key=api_key, token=token)


@api_keys_router.get("")
def list_route(db: DB, user: SessionAuth) -> list[ApiKey]:
    return service.owned_by(db, user).fetch_models()


@api_keys_router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_route(db: DB, user: SessionAuth, api_key_id: int) -> None:
    service.revoke(db, service.find_owned(db, user, api_key_id))
