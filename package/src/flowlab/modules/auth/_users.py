from typing import Any

from fastapi import HTTPException, status

from flowlab._database import INTEGRITY_ERRORS
from flowlab.modules.auth import _api_keys as api_keys
from flowlab.modules.auth._email import normalize_email
from flowlab.modules.auth._models import BaseUser, user_model
from flowlab.modules.auth._security import (
    PasswordTooLong,
    TokenExpired,
    TokenInvalid,
    burn_dummy_password_check,
    decode_token,
    hash_password,
    is_api_key,
    mint_token,
    verify_password,
)
from flowlab.modules.db import now
from flowlab.modules.db.database import DB as Database


def find_by_email(db: Database, email: str) -> BaseUser | None:
    return (
        db.select_models(user_model())
        .where_equals("email", normalize_email(email))
        .where_is_null("deleted_at")
        .fetch_model()
    )


def register(db: Database, email: str, password: str, attributes: dict[str, Any] | None = None) -> BaseUser:
    email = normalize_email(email)

    if find_by_email(db, email) is not None:
        raise email_conflict()

    try:
        user = user_model()(**(attributes or {}), email=email, password=hash_password(password))
    except PasswordTooLong as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from None

    try:
        db.insert_model(user).omit_null_values().returning().execute()
    except INTEGRITY_ERRORS:
        raise email_conflict() from None

    return user


def login(db: Database, email: str, password: str) -> BaseUser:
    user = find_by_email(db, email)

    if user is None:
        burn_dummy_password_check(password)
        raise invalid_credentials()

    if not verify_password(password, user.password):
        raise invalid_credentials()

    return user


def issue_token(user: BaseUser) -> str:
    if user.id is None:
        raise ValueError("cannot issue a token for a user that has no id")

    return mint_token(str(user.id))


def user_from_token(db: Database, token: str) -> BaseUser:
    try:
        payload = decode_token(token)
    except TokenExpired:
        raise unauthenticated("Token has expired") from None
    except TokenInvalid:
        raise unauthenticated("Invalid token") from None

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise unauthenticated("Invalid token") from None

    user = db.select_models(user_model()).where_equals("id", user_id).where_is_null("deleted_at").fetch_model()

    if user is None:
        raise unauthenticated("User no longer exists")

    return user


def user_from_api_key(db: Database, token: str) -> BaseUser:
    user = api_keys.user_from_api_key(db, token)

    if user is None:
        raise unauthenticated("Invalid API key")

    return user


def user_from_credential(db: Database, credential: str) -> BaseUser:
    if is_api_key(credential):
        return user_from_api_key(db, credential)

    return user_from_token(db, credential)


def soft_delete(db: Database, user: BaseUser) -> None:
    db.update(type(user).__table__).updates({"deleted_at": now(), "updated_at": now()}).where_equals(
        "id", user.id
    ).execute()


def email_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Email is already registered",
    )


def invalid_credentials() -> HTTPException:
    return unauthenticated("Incorrect email or password")


def unauthenticated(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
