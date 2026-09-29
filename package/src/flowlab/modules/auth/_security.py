import contextlib
import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any

import bcrypt
import jwt

from flowlab._settings import AuthSettings
from flowlab._state import get_app

ALGORITHM = "HS256"

MAX_PASSWORD_BYTES = 72

API_KEY_PREFIX = "flk_"

API_KEY_HINT_LENGTH = len(API_KEY_PREFIX) + 8

_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt())


def get_auth_settings() -> AuthSettings:
    return get_app().auth


class PasswordTooLong(ValueError):
    def __init__(self) -> None:
        super().__init__(f"password may not exceed {MAX_PASSWORD_BYTES} bytes")


class TokenExpired(Exception):
    pass


class TokenInvalid(Exception):
    pass


def encode_password(password: str) -> bytes:
    encoded = password.encode()

    if len(encoded) > MAX_PASSWORD_BYTES:
        raise PasswordTooLong

    return encoded


def hash_password(password: str) -> str:
    return bcrypt.hashpw(encode_password(password), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(encode_password(password), hashed.encode())
    except ValueError:
        return False


def burn_dummy_password_check(password: str) -> None:
    with contextlib.suppress(PasswordTooLong):
        bcrypt.checkpw(encode_password(password), _DUMMY_HASH)


def mint_token(subject: str) -> str:
    settings = get_auth_settings()
    now = datetime.now(UTC)

    return jwt.encode(
        {"sub": subject, "iat": now, "exp": now + settings.jwt_ttl},
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(token, get_auth_settings().jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise TokenExpired from None
    except jwt.InvalidTokenError:
        raise TokenInvalid from None

    return payload


def generate_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def is_api_key(credential: str) -> bool:
    return credential.startswith(API_KEY_PREFIX)
