from __future__ import annotations

import datetime
from typing import ClassVar

from pydantic import ConfigDict, Field

from flowlab.modules.db.orm import AutoIncrement, Model

RESERVED_USER_FIELDS = frozenset({"id", "email", "password", "created_at", "updated_at", "deleted_at"})


class BaseUser(Model):
    __table__ = "users"
    __fillable__: ClassVar[tuple[str, ...]] = ()

    model_config = ConfigDict(validate_assignment=True)

    id: AutoIncrement = None
    email: str
    password: str = Field(exclude=True)
    created_at: datetime.datetime | None = None
    updated_at: datetime.datetime | None = None
    deleted_at: datetime.datetime | None = None


class User(BaseUser):
    pass


class ApiKey(Model):
    __table__ = "api_keys"

    model_config = ConfigDict(validate_assignment=True)

    id: AutoIncrement = None
    user_id: int
    name: str
    hint: str
    token_hash: str = Field(exclude=True)
    created_at: datetime.datetime | None = None
    updated_at: datetime.datetime | None = None
    deleted_at: datetime.datetime | None = None


def fillable_fields(user_model: type[BaseUser]) -> tuple[str, ...]:
    fillable = tuple(user_model.__fillable__)

    for name in fillable:
        if name in RESERVED_USER_FIELDS:
            raise TypeError(f"{user_model.__name__}.__fillable__ may not contain {name!r}; auth manages it")

        if name not in user_model.model_fields:
            raise TypeError(f"{user_model.__name__}.__fillable__ names {name!r}, which is not a field of the model")

    return fillable


def user_model() -> type[BaseUser]:
    from flowlab._state import get_app

    return get_app().user_model
