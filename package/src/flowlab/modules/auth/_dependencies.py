from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from flowlab._database import DB
from flowlab.modules.auth._models import BaseUser
from flowlab.modules.auth._security import is_api_key
from flowlab.modules.auth._users import unauthenticated, user_from_credential, user_from_token

bearer_scheme = HTTPBearer(auto_error=False)

BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def get_user(db: DB, credentials: BearerCredentials = None) -> BaseUser:
    if credentials is None:
        raise unauthenticated("Not authenticated")

    return user_from_credential(db, credentials.credentials)


def get_session_user(db: DB, credentials: BearerCredentials = None) -> BaseUser:
    if credentials is None:
        raise unauthenticated("Not authenticated")

    if is_api_key(credentials.credentials):
        raise unauthenticated("This endpoint requires a login token, not an API key")

    return user_from_token(db, credentials.credentials)


Auth = Annotated[BaseUser, Depends(get_user)]

SessionAuth = Annotated[BaseUser, Depends(get_session_user)]
