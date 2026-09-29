from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, Self, TypeVar

from flowlab.modules.db.orm._loader import load_relations
from flowlab.modules.db.orm._mapper import model_mapper
from flowlab.modules.db.orm._model import Model
from flowlab.modules.db.orm._tree import RelationTree
from flowlab.modules.db.query import SelectQuery

if TYPE_CHECKING:
    from collections.abc import Callable

    from flowlab.modules.db.database import DatabaseABC
    from flowlab.modules.db.dialects import DialectABC


ModelT = TypeVar("ModelT", bound=Model)


class SelectModelQuery(SelectQuery, Generic[ModelT]):
    def __init__(self, dialect: DialectABC, database: DatabaseABC, model: type[ModelT]) -> None:
        mapper = model_mapper(model)

        super().__init__(dialect, mapper.meta.table, database)

        self._mapper = mapper
        self._tree = RelationTree(model)

        self.columns(mapper.meta.column_identifiers())

    def relation(self, path: str, customize: Callable[[SelectQuery], Any] | None = None) -> Self:
        self._tree.add(path, customize)

        return self

    def fetch_models(self, emulate_prepare: bool = False) -> list[ModelT]:
        rows = self.execute(emulate_prepare).fetch_dicts()
        models = self._mapper.to_models(rows)
        parents: list[Model] = list(models)

        load_relations(self._database, parents, self._tree.nodes, emulate_prepare)

        return models

    def fetch_model(self, emulate_prepare: bool = False) -> ModelT | None:
        self.limit(1)
        models = self.fetch_models(emulate_prepare)

        return models[0] if len(models) > 0 else None
