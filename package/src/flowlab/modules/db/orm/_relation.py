from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeAlias, TypeVar

from pydantic.fields import FieldInfo

from flowlab.modules.db import ModelError
from flowlab.modules.db.orm.enums import RelationEnum

if TYPE_CHECKING:
    from flowlab.modules.db.orm._model import Model


_SNAKE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _snake_case(name: str) -> str:
    return _SNAKE_BOUNDARY.sub("_", name).lower()


@dataclass(frozen=True)
class RelationInfo:
    relation: RelationEnum
    foreign_key: str | None = None
    primary_key: str | None = None
    through: str | None = None
    through_foreign_key: str | None = None
    through_primary_key: str | None = None


def _relation_field(info: RelationInfo, many: bool) -> Any:
    field_info = FieldInfo(default_factory=list) if many else FieldInfo(default=None)
    field_info.metadata.append(info)

    return field_info


def has_one(foreign_key: str | None = None, primary_key: str | None = None) -> Any:
    """One related row pointing back at this model.

    ``foreign_key`` is the column on the related table, defaulting to
    ``<this_model>_<this_primary_key>``; ``primary_key`` is the column on this
    model's table it references, defaulting to this model's primary key."""
    info = RelationInfo(relation=RelationEnum.HAS_ONE, foreign_key=foreign_key, primary_key=primary_key)

    return _relation_field(info, many=False)


def belongs_to(foreign_key: str | None = None, primary_key: str | None = None) -> Any:
    """The single row this model points at.

    ``foreign_key`` is the column on this model's table, defaulting to
    ``<related_model>_<related_primary_key>``; ``primary_key`` is the column on
    the related table it references, defaulting to the related primary key."""
    info = RelationInfo(relation=RelationEnum.BELONGS_TO, foreign_key=foreign_key, primary_key=primary_key)

    return _relation_field(info, many=False)


def has_many(foreign_key: str | None = None, primary_key: str | None = None) -> Any:
    """Every related row pointing back at this model. Keys work as in ``has_one``."""
    info = RelationInfo(relation=RelationEnum.HAS_MANY, foreign_key=foreign_key, primary_key=primary_key)

    return _relation_field(info, many=True)


def many_to_many(
    through: str,
    through_primary_key: str | None = None,
    through_foreign_key: str | None = None,
    primary_key: str | None = None,
    foreign_key: str | None = None,
) -> Any:
    """Every related row reachable through the ``through`` join table.

    ``through_primary_key`` is that table's column pointing at this model,
    defaulting to ``<this_model>_<this_primary_key>``, and
    ``through_foreign_key`` its column pointing at the related model,
    defaulting to ``<related_model>_<related_primary_key>``. ``primary_key``
    and ``foreign_key`` name the columns those reference, each defaulting to
    the primary key on its side."""
    info = RelationInfo(
        relation=RelationEnum.MANY_TO_MANY,
        foreign_key=foreign_key,
        primary_key=primary_key,
        through=through,
        through_foreign_key=through_foreign_key,
        through_primary_key=through_primary_key,
    )

    return _relation_field(info, many=True)


class ModelRelation:
    def __init__(
        self, field_name: str, info: RelationInfo, owner: type[Model], target: type[Model], many: bool
    ) -> None:
        self._field_name = field_name
        self._info = info
        self._owner = owner
        self._target = target
        self._many = many

        self._owner_column: str | None = None
        self._target_column: str | None = None
        self._through_owner_column: str | None = None
        self._through_target_column: str | None = None

    @property
    def field_name(self) -> str:
        return self._field_name

    @property
    def relation(self) -> RelationEnum:
        return self._info.relation

    @property
    def owner(self) -> type[Model]:
        return self._owner

    @property
    def target(self) -> type[Model]:
        return self._target

    @property
    def many(self) -> bool:
        return self._many

    @property
    def through(self) -> str:
        if self._info.through is None:
            raise ModelError(f"relation {self._describe()} has no join table")

        return self._info.through

    @property
    def owner_column(self) -> str:
        if self._owner_column is None:
            self._resolve()

        assert self._owner_column is not None

        return self._owner_column

    @property
    def target_column(self) -> str:
        if self._target_column is None:
            self._resolve()

        assert self._target_column is not None

        return self._target_column

    @property
    def through_owner_column(self) -> str:
        if self._through_owner_column is None:
            self._resolve()

        if self._through_owner_column is None:
            raise ModelError(f"relation {self._describe()} has no join table")

        return self._through_owner_column

    @property
    def through_target_column(self) -> str:
        if self._through_target_column is None:
            self._resolve()

        if self._through_target_column is None:
            raise ModelError(f"relation {self._describe()} has no join table")

        return self._through_target_column

    def _describe(self) -> str:
        return f"{self._owner.__name__}.{self._field_name}"

    def _default_foreign_key(self, model: type[Model]) -> str:
        return f"{_snake_case(model.__name__)}_{self._primary_key(model)}"

    def _primary_key(self, model: type[Model]) -> str:
        from flowlab.modules.db.orm._meta import model_meta

        return model_meta(model).primary_key.column_name

    def _resolve(self) -> None:
        if self._info.relation == RelationEnum.BELONGS_TO:
            self._owner_column = self._info.foreign_key or self._default_foreign_key(self._target)
            self._target_column = self._info.primary_key or self._primary_key(self._target)
            return

        if self._info.relation == RelationEnum.MANY_TO_MANY:
            self._owner_column = self._info.primary_key or self._primary_key(self._owner)
            self._target_column = self._info.foreign_key or self._primary_key(self._target)
            self._through_owner_column = self._info.through_primary_key or self._default_foreign_key(self._owner)
            self._through_target_column = self._info.through_foreign_key or self._default_foreign_key(self._target)
            return

        self._owner_column = self._info.primary_key or self._primary_key(self._owner)
        self._target_column = self._info.foreign_key or self._default_foreign_key(self._owner)


RelationT = TypeVar("RelationT")

HasOne: TypeAlias = RelationT | None

BelongsTo: TypeAlias = RelationT | None

HasMany: TypeAlias = list[RelationT]

ManyToMany: TypeAlias = list[RelationT]
