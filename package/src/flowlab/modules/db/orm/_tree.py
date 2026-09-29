from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from flowlab.modules.db import ModelError
from flowlab.modules.db.orm._meta import model_meta
from flowlab.modules.db.orm._relation import ModelRelation

if TYPE_CHECKING:
    from flowlab.modules.db.orm._model import Model
    from flowlab.modules.db.query import SelectQuery


class RelationNode:
    def __init__(self, relation: ModelRelation) -> None:
        self._relation = relation
        self._customize: Callable[[SelectQuery], Any] | None = None
        self._children: dict[str, RelationNode] = {}

    @property
    def relation(self) -> ModelRelation:
        return self._relation

    @property
    def customize(self) -> Callable[[SelectQuery], Any] | None:
        return self._customize

    @property
    def children(self) -> dict[str, RelationNode]:
        return self._children

    def set_customize(self, customize: Callable[[SelectQuery], Any] | None) -> None:
        if customize is not None:
            self._customize = customize

    def child(self, field_name: str) -> RelationNode:
        node = self._children.get(field_name)

        if node is None:
            node = RelationNode(model_meta(self._relation.target).relation(field_name))
            self._children[field_name] = node

        return node


class RelationTree:
    def __init__(self, model: type[Model]) -> None:
        self._model = model
        self._nodes: dict[str, RelationNode] = {}

    @property
    def nodes(self) -> dict[str, RelationNode]:
        return self._nodes

    @property
    def is_empty(self) -> bool:
        return len(self._nodes) == 0

    def add(self, path: str, customize: Callable[[SelectQuery], Any] | None = None) -> None:
        segments = [segment.strip() for segment in path.split(".")]

        if len(segments) == 0 or any(len(segment) == 0 for segment in segments):
            raise ModelError(f"relation path {path!r} is not a dot separated chain of relation names")

        node = self._nodes.get(segments[0])

        if node is None:
            node = RelationNode(model_meta(self._model).relation(segments[0]))
            self._nodes[segments[0]] = node

        for segment in segments[1:]:
            node = node.child(segment)

        node.set_customize(customize)
