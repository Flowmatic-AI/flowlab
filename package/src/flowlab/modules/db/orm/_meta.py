from __future__ import annotations

from typing import TYPE_CHECKING, Any, get_args

from flowlab.modules.db import ModelError
from flowlab.modules.db.orm._column import ColumnInfo, ModelColumn
from flowlab.modules.db.orm._relation import ModelRelation, RelationInfo
from flowlab.modules.db.orm.enums import RelationEnum

if TYPE_CHECKING:
    from flowlab.modules.db.orm._model import Model


_MANY_RELATIONS = (RelationEnum.HAS_MANY, RelationEnum.MANY_TO_MANY)


class ModelMeta:
    def __init__(
        self,
        model: type[Model],
        table: str,
        columns: list[ModelColumn],
        relations: dict[str, ModelRelation],
    ) -> None:
        self._model = model
        self._table = table
        self._columns = columns
        self._relations = relations

        self._columns_by_field = {column.field_name: column for column in columns}
        self._columns_by_name = {column.column_name: column for column in columns}
        self._primary_keys = [column for column in columns if column.primary_key]

    @property
    def model(self) -> type[Model]:
        return self._model

    @property
    def table(self) -> str:
        return self._table

    @property
    def columns(self) -> list[ModelColumn]:
        return list(self._columns)

    @property
    def relations(self) -> dict[str, ModelRelation]:
        return dict(self._relations)

    @property
    def primary_keys(self) -> list[ModelColumn]:
        if len(self._primary_keys) == 0:
            raise ModelError(
                f"model {self._model.__name__} declares no primary key: annotate a field with "
                "AutoIncrement, PrimaryKey[...] or column(primary_key=True)"
            )

        return list(self._primary_keys)

    @property
    def primary_key(self) -> ModelColumn:
        primary_keys = self.primary_keys

        if len(primary_keys) > 1:
            names = ", ".join(column.column_name for column in primary_keys)
            raise ModelError(
                f"model {self._model.__name__} has a composite primary key ({names}), which relations "
                "cannot match against: name the single column to use on the relation instead"
            )

        return primary_keys[0]

    def column_by_field(self, field_name: str) -> ModelColumn:
        column = self._columns_by_field.get(field_name)

        if column is None:
            raise ModelError(f"model {self._model.__name__} has no column field {field_name!r}")

        return column

    def column_by_name(self, column_name: str) -> ModelColumn:
        column = self._columns_by_name.get(column_name)

        if column is None:
            raise ModelError(
                f"model {self._model.__name__} maps no field to column {column_name!r} of table {self._table!r}"
            )

        return column

    def relation(self, field_name: str) -> ModelRelation:
        relation = self._relations.get(field_name)

        if relation is None:
            available = ", ".join(sorted(self._relations)) or "none"
            raise ModelError(
                f"model {self._model.__name__} has no relation {field_name!r} (declared relations: {available})"
            )

        return relation

    def column_identifiers(self) -> dict[str, list[str]]:
        return {column.column_name: [self._table, column.column_name] for column in self._columns}


def _relation_info(metadata: list[Any]) -> RelationInfo | None:
    for entry in metadata:
        if isinstance(entry, RelationInfo):
            return entry

    return None


def _column_info(metadata: list[Any]) -> ColumnInfo | None:
    for entry in metadata:
        if isinstance(entry, ColumnInfo):
            return entry

    return None


def _target_model(annotation: Any) -> type[Model] | None:
    from flowlab.modules.db.orm._model import Model

    if isinstance(annotation, type) and issubclass(annotation, Model):
        return annotation

    for argument in get_args(annotation):
        target = _target_model(argument)

        if target is not None:
            return target

    return None


def build_model_meta(model: type[Model]) -> ModelMeta:
    if not model.__table__:
        raise ModelError(f"model {model.__name__} has no __table__: set it to the table name the model maps to")

    if not model.__pydantic_complete__:
        model.model_rebuild()

    columns: list[ModelColumn] = []
    relations: dict[str, ModelRelation] = {}

    for field_name, field_info in model.model_fields.items():
        relation_info = _relation_info(field_info.metadata)

        if relation_info is not None:
            target = _target_model(field_info.annotation)

            if target is None:
                raise ModelError(
                    f"relation {model.__name__}.{field_name} is annotated {field_info.annotation!r}, which names "
                    "no Model: annotate it with the related model, e.g. HasMany[Post] or Post | None"
                )

            relations[field_name] = ModelRelation(
                field_name=field_name,
                info=relation_info,
                owner=model,
                target=target,
                many=relation_info.relation in _MANY_RELATIONS,
            )
            continue

        column_info = _column_info(field_info.metadata) or ColumnInfo()

        columns.append(
            ModelColumn(
                field_name=field_name,
                column_name=column_info.column_name or field_name,
                primary_key=column_info.primary_key,
                auto_increment=column_info.auto_increment,
            )
        )

    return ModelMeta(model=model, table=model.__table__, columns=columns, relations=relations)


_META_CACHE: dict[type[Model], ModelMeta] = {}


def model_meta(model: type[Model]) -> ModelMeta:
    meta = _META_CACHE.get(model)

    if meta is None:
        meta = build_model_meta(model)
        _META_CACHE[model] = meta

    return meta
