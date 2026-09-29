from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Generic, Self, TypeVar

from flowlab.modules.db import ModelError
from flowlab.modules.db.orm._mapper import model_mapper
from flowlab.modules.db.orm._meta import model_meta
from flowlab.modules.db.orm._relation import ModelRelation
from flowlab.modules.db.orm._tree import RelationNode, RelationTree

if TYPE_CHECKING:
    from flowlab.modules.db.database import DatabaseABC
    from flowlab.modules.db.dialects import DialectABC
    from flowlab.modules.db.orm._column import ModelColumn
    from flowlab.modules.db.orm._model import Model

ModelT = TypeVar("ModelT", bound="Model")


class UpdateModelQuery(Generic[ModelT]):
    def __init__(self, dialect: DialectABC, database: DatabaseABC, models: list[ModelT]) -> None:
        if len(models) > 0:
            classes = {type(model) for model in models}

            if len(classes) > 1:
                names = ", ".join(sorted(model_class.__name__ for model_class in classes))
                raise ModelError(f"update_models requires a single model class, got {names}")

        self._dialect = dialect
        self._database = database
        self._models = models
        self._model: type[Model] | None = type(models[0]) if len(models) > 0 else None
        self._tree = RelationTree(self._model) if self._model is not None else None
        self._column_names: list[str] | None = None

    def relation(self, path: str) -> Self:
        if self._tree is not None:
            self._tree.add(path)

        return self

    def columns(self, column_names: list[str]) -> Self:
        self._column_names = column_names

        return self

    def execute(self, emulate_prepare: bool = False) -> list[ModelT]:
        if self._model is None:
            return self._models

        meta = model_meta(self._model)

        if self._column_names is None:
            columns = meta.columns
        else:
            columns = [meta.column_by_name(name) for name in self._column_names]

        for model in self._models:
            _update_model(self._database, model, columns, emulate_prepare)

        if self._tree is not None:
            for node in self._tree.nodes.values():
                _cascade(self._database, self._models, node, emulate_prepare)

        return self._models


def _update_model(database: DatabaseABC, model: Model, columns: list[ModelColumn], emulate_prepare: bool) -> None:
    mapper = model_mapper(type(model))
    meta = mapper.meta
    primary_key_values: list[tuple[str, Any]] = []

    for primary_key in meta.primary_keys:
        value = mapper.column_value(model, primary_key)

        if value is None:
            raise ModelError(
                f"{type(model).__name__} has no {primary_key.column_name} value: it has to be inserted "
                "before it can be updated"
            )

        primary_key_values.append((primary_key.column_name, value))

    updates = {column.column_name: mapper.column_value(model, column) for column in columns if not column.primary_key}

    if len(updates) == 0:
        return

    query = database.update(meta.table).updates(updates)

    for column_name, value in primary_key_values:
        query.where_equals([meta.table, column_name], value)

    query.execute(emulate_prepare)


def _cascade(database: DatabaseABC, parents: Sequence[Model], node: RelationNode, emulate_prepare: bool) -> None:
    relation = node.relation
    meta = model_meta(relation.target)
    children = _related(parents, relation)

    if len(children) == 0:
        return

    for child in children:
        _update_model(database, child, meta.columns, emulate_prepare)

    for child_node in node.children.values():
        _cascade(database, children, child_node, emulate_prepare)


def _related(parents: Sequence[Model], relation: ModelRelation) -> list[Model]:
    children: list[Model] = []
    seen: set[int] = set()

    for parent in parents:
        for child in model_mapper(type(parent)).related_models(parent, relation):
            if id(child) in seen:
                continue

            seen.add(id(child))
            children.append(child)

    return children
