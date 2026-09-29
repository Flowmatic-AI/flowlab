from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Generic, Self, TypeVar

from flowlab.modules.db import ModelError
from flowlab.modules.db.orm._loader import load_relations, owner_keys
from flowlab.modules.db.orm._mapper import model_mapper
from flowlab.modules.db.orm._meta import model_meta
from flowlab.modules.db.orm._tree import RelationTree
from flowlab.modules.db.orm.enums import RelationEnum

if TYPE_CHECKING:
    from flowlab.modules.db.database import DatabaseABC
    from flowlab.modules.db.dialects import DialectABC
    from flowlab.modules.db.orm._model import Model
    from flowlab.modules.db.orm._relation import ModelRelation
    from flowlab.modules.db.orm._tree import RelationNode

ModelT = TypeVar("ModelT", bound="Model")


class DeleteModelQuery(Generic[ModelT]):
    def __init__(self, dialect: DialectABC, database: DatabaseABC, models: list[ModelT]) -> None:
        if len(models) > 0:
            classes = {type(model) for model in models}

            if len(classes) > 1:
                names = ", ".join(sorted(model_class.__name__ for model_class in classes))
                raise ModelError(f"delete_models requires a single model class, got {names}")

        self._dialect = dialect
        self._database = database
        self._models = models
        self._model: type[Model] | None = type(models[0]) if len(models) > 0 else None
        self._tree = RelationTree(self._model) if self._model is not None else None

    def relation(self, path: str) -> Self:
        if self._tree is not None:
            self._tree.add(path)

        return self

    def execute(self, emulate_prepare: bool = False) -> None:
        if self._model is None or len(self._models) == 0:
            return

        nodes = self._tree.nodes if self._tree is not None else {}
        pending = _process_nodes(self._database, self._models, nodes, emulate_prepare)

        _delete_owners(self._database, self._model, self._models, emulate_prepare)

        for node, keys in pending:
            _delete_belongs_to_target(self._database, node, keys, emulate_prepare)


def _process_nodes(
    database: DatabaseABC,
    owners: Sequence[Model],
    nodes: dict[str, RelationNode],
    emulate_prepare: bool,
) -> list[tuple[RelationNode, list[Any]]]:
    pending: list[tuple[RelationNode, list[Any]]] = []

    for node in nodes.values():
        relation = node.relation

        if relation.relation == RelationEnum.MANY_TO_MANY:
            if len(node.children) > 0:
                raise ModelError(
                    f"relation {relation.owner.__name__}.{relation.field_name} cannot cascade delete past its "
                    "join table"
                )

            keys = owner_keys(owners, relation.owner_column)
            _delete_where_in(database, relation.through, relation.through_owner_column, keys, emulate_prepare)
            continue

        if relation.relation == RelationEnum.BELONGS_TO:
            pending.append((node, owner_keys(owners, relation.owner_column)))
            continue

        _process_has_relation(database, owners, node, emulate_prepare, pending)

    return pending


def _process_has_relation(
    database: DatabaseABC,
    owners: Sequence[Model],
    node: RelationNode,
    emulate_prepare: bool,
    pending: list[tuple[RelationNode, list[Any]]],
) -> None:
    relation = node.relation
    table = model_meta(relation.target).table
    keys = owner_keys(owners, relation.owner_column)

    if len(keys) == 0:
        return

    if len(node.children) == 0:
        _delete_where_in(database, table, relation.target_column, keys, emulate_prepare)
        return

    load_relations(database, owners, {relation.field_name: node}, emulate_prepare)
    children = _related_models(owners, relation)
    child_pending = _process_nodes(database, children, node.children, emulate_prepare)

    _delete_where_in(database, table, relation.target_column, keys, emulate_prepare)

    for child_node, child_keys in child_pending:
        _delete_belongs_to_target(database, child_node, child_keys, emulate_prepare)


def _delete_belongs_to_target(
    database: DatabaseABC,
    node: RelationNode,
    keys: list[Any],
    emulate_prepare: bool,
) -> None:
    if len(keys) == 0:
        return

    relation = node.relation
    table = model_meta(relation.target).table

    if len(node.children) == 0:
        _delete_where_in(database, table, relation.target_column, keys, emulate_prepare)
        return

    targets = _load_by_column(database, relation.target, relation.target_column, keys, emulate_prepare)
    child_pending = _process_nodes(database, targets, node.children, emulate_prepare)

    _delete_where_in(database, table, relation.target_column, keys, emulate_prepare)

    for child_node, child_keys in child_pending:
        _delete_belongs_to_target(database, child_node, child_keys, emulate_prepare)


def _load_by_column(
    database: DatabaseABC,
    model: type[Model],
    column_name: str,
    keys: list[Any],
    emulate_prepare: bool,
) -> list[Model]:
    mapper = model_mapper(model)
    meta = mapper.meta
    query = database.select(meta.table).columns(meta.column_identifiers())
    query.where_in([meta.table, column_name], keys)

    return mapper.to_models(query.execute(emulate_prepare).fetch_dicts())


def _delete_owners(
    database: DatabaseABC,
    model: type[Model],
    models: Sequence[Model],
    emulate_prepare: bool,
) -> None:
    mapper = model_mapper(model)
    meta = mapper.meta
    primary_keys = meta.primary_keys

    if len(primary_keys) == 1:
        primary_key = primary_keys[0]
        keys: list[Any] = []

        for owner in models:
            value = mapper.column_value(owner, primary_key)

            if value is None:
                raise ModelError(
                    f"{model.__name__} has no {primary_key.column_name} value: it has to be inserted before "
                    "it can be deleted"
                )

            keys.append(value)

        _delete_where_in(database, meta.table, primary_key.column_name, keys, emulate_prepare)
        return

    for owner in models:
        query = database.delete(meta.table)

        for primary_key in primary_keys:
            value = mapper.column_value(owner, primary_key)

            if value is None:
                raise ModelError(
                    f"{model.__name__} has no {primary_key.column_name} value: it has to be inserted before "
                    "it can be deleted"
                )

            query.where_equals([meta.table, primary_key.column_name], value)

        query.execute(emulate_prepare)


def _delete_where_in(
    database: DatabaseABC, table: str, column_name: str, keys: list[Any], emulate_prepare: bool
) -> None:
    if len(keys) == 0:
        return

    database.delete(table).where_in([table, column_name], keys).execute(emulate_prepare)


def _related_models(owners: Sequence[Model], relation: ModelRelation) -> list[Model]:
    children: list[Model] = []
    seen: set[int] = set()

    for owner in owners:
        for child in model_mapper(type(owner)).related_models(owner, relation):
            if id(child) in seen:
                continue

            seen.add(id(child))
            children.append(child)

    return children
