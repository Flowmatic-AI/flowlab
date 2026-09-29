from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from flowlab.modules.db.orm._mapper import model_mapper
from flowlab.modules.db.orm.enums import RelationEnum

if TYPE_CHECKING:
    from flowlab.modules.db.database import DatabaseABC
    from flowlab.modules.db.orm._model import Model
    from flowlab.modules.db.orm._tree import RelationNode


OWNER_KEY_ALIAS = "__relation_owner_key__"


def owner_keys(parents: Sequence[Model], owner_column: str) -> list[Any]:
    keys: list[Any] = []
    seen: set[Any] = set()

    for parent in parents:
        key = model_mapper(type(parent)).key_value(parent, owner_column)

        if key is None or key in seen:
            continue

        seen.add(key)
        keys.append(key)

    return keys


def load_relations(
    database: DatabaseABC,
    parents: Sequence[Model],
    nodes: dict[str, RelationNode],
    emulate_prepare: bool = False,
) -> None:
    if len(parents) == 0 or len(nodes) == 0:
        return

    for node in nodes.values():
        children = _load_node(database, parents, node, emulate_prepare)
        load_relations(database, children, node.children, emulate_prepare)


def _load_node(
    database: DatabaseABC,
    parents: Sequence[Model],
    node: RelationNode,
    emulate_prepare: bool,
) -> list[Model]:
    relation = node.relation
    keys = owner_keys(parents, relation.owner_column)

    if len(keys) == 0:
        _attach(parents, node, {})
        return []

    if relation.relation == RelationEnum.MANY_TO_MANY:
        grouped = _load_many_to_many(database, node, keys, emulate_prepare)
    else:
        grouped = _load_direct(database, node, keys, emulate_prepare)

    _attach(parents, node, grouped)

    children: list[Model] = []
    seen: set[int] = set()

    for group in grouped.values():
        for child in group:
            if id(child) in seen:
                continue

            seen.add(id(child))
            children.append(child)

    return children


def _load_direct(
    database: DatabaseABC,
    node: RelationNode,
    keys: list[Any],
    emulate_prepare: bool,
) -> dict[Any, list[Model]]:
    relation = node.relation
    mapper = model_mapper(relation.target)
    meta = mapper.meta

    identifiers = meta.column_identifiers()
    identifiers[relation.target_column] = [meta.table, relation.target_column]

    query = database.select(meta.table).columns(identifiers)
    query.where_in([meta.table, relation.target_column], keys)

    if node.customize is not None:
        node.customize(query)

    grouped: dict[Any, list[Model]] = {}

    for row in query.execute(emulate_prepare).fetch_dicts():
        grouped.setdefault(row[relation.target_column], []).append(mapper.to_model(row))

    return grouped


def _load_many_to_many(
    database: DatabaseABC,
    node: RelationNode,
    keys: list[Any],
    emulate_prepare: bool,
) -> dict[Any, list[Model]]:
    relation = node.relation
    mapper = model_mapper(relation.target)
    meta = mapper.meta
    through = relation.through

    identifiers = meta.column_identifiers()
    identifiers[relation.target_column] = [meta.table, relation.target_column]
    identifiers[OWNER_KEY_ALIAS] = [through, relation.through_owner_column]

    query = database.select(meta.table).columns(identifiers)
    query.inner_join(
        through,
        lambda join: join.on([through, relation.through_target_column], [meta.table, relation.target_column]),
    )
    query.where_in([through, relation.through_owner_column], keys)

    if node.customize is not None:
        node.customize(query)

    instances: dict[Any, Model] = {}
    grouped: dict[Any, list[Model]] = {}
    linked: set[tuple[Any, Any]] = set()

    for row in query.execute(emulate_prepare).fetch_dicts():
        identity = row[relation.target_column]
        owner_key = row[OWNER_KEY_ALIAS]

        instance = instances.get(identity)

        if instance is None:
            instance = mapper.to_model(row)
            instances[identity] = instance

        if (owner_key, identity) in linked:
            continue

        linked.add((owner_key, identity))
        grouped.setdefault(owner_key, []).append(instance)

    return grouped


def _attach(parents: Sequence[Model], node: RelationNode, grouped: dict[Any, list[Model]]) -> None:
    relation = node.relation

    for parent in parents:
        mapper = model_mapper(type(parent))
        matches = grouped.get(mapper.key_value(parent, relation.owner_column), [])

        if relation.many:
            mapper.set_relation(parent, relation, list(matches))
            continue

        mapper.set_relation(parent, relation, matches[0] if len(matches) > 0 else None)
