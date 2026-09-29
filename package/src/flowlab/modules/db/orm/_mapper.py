from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from flowlab.modules.db.orm._meta import model_meta
from flowlab.modules.db.orm._model import Model

if TYPE_CHECKING:
    from collections.abc import Sequence

    from flowlab.modules.db.database import DatabaseABC
    from flowlab.modules.db.orm._column import ModelColumn
    from flowlab.modules.db.orm._meta import ModelMeta
    from flowlab.modules.db.orm._relation import ModelRelation
    from flowlab.modules.db.query.ddl import TableDescription


ModelT = TypeVar("ModelT", bound=Model)


class ModelMapper(Generic[ModelT]):
    """Maps rows of one table onto one model class, and reads its fields back out.

    A model is a bare pydantic struct: it declares ``__table__``, its columns and
    its relations, and nothing else. Everything that moves values between a row
    and a model — ``to_model()``/``to_row()`` — and every read or write of a field
    by column or relation lives here instead."""

    def __init__(self, model: type[ModelT]) -> None:
        self._model = model
        self._meta = model_meta(model)

    @property
    def model(self) -> type[ModelT]:
        return self._model

    @property
    def meta(self) -> ModelMeta:
        return self._meta

    def describe_table(self, database: DatabaseABC) -> TableDescription:
        return database.describe_table(self._meta.table)

    def to_model(self, row: dict[str, Any]) -> ModelT:
        values: dict[str, Any] = {}

        for column in self._meta.columns:
            if column.column_name in row:
                values[column.field_name] = row[column.column_name]

        return self._model.model_validate(values)

    def to_models(self, rows: Sequence[dict[str, Any]]) -> list[ModelT]:
        return [self.to_model(row) for row in rows]

    def to_row(self, model: ModelT) -> dict[str, Any]:
        return {column.column_name: model.__dict__[column.field_name] for column in self._meta.columns}

    def column_value(self, model: ModelT, column: ModelColumn) -> Any:
        return model.__dict__[column.field_name]

    def set_column_value(self, model: ModelT, column: ModelColumn, value: Any) -> None:
        model.__dict__[column.field_name] = value
        model.__pydantic_fields_set__.add(column.field_name)

    def key_value(self, model: ModelT, column_name: str) -> Any:
        return model.__dict__[self._meta.column_by_name(column_name).field_name]

    def primary_key_value(self, model: ModelT) -> Any:
        return model.__dict__[self._meta.primary_key.field_name]

    def related_models(self, model: ModelT, relation: ModelRelation) -> list[Model]:
        value = model.__dict__[relation.field_name]

        if value is None:
            return []

        if isinstance(value, Model):
            return [value]

        if isinstance(value, list):
            return [entry for entry in value if isinstance(entry, Model)]

        return []

    def set_relation(self, model: ModelT, relation: ModelRelation, value: Any) -> None:
        model.__dict__[relation.field_name] = value
        model.__pydantic_fields_set__.add(relation.field_name)

    def is_relation_loaded(self, model: ModelT, field_name: str) -> bool:
        return self._meta.relation(field_name).field_name in model.__pydantic_fields_set__


_MAPPER_CACHE: dict[type[Model], ModelMapper[Any]] = {}


def model_mapper(model: type[ModelT]) -> ModelMapper[ModelT]:
    mapper = _MAPPER_CACHE.get(model)

    if mapper is None:
        mapper = ModelMapper(model)
        _MAPPER_CACHE[model] = mapper

    return mapper
