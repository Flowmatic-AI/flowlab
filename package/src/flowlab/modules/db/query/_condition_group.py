from __future__ import annotations

from abc import ABC, abstractmethod

from flowlab.modules.db.query._condition import Condition
from flowlab.modules.db.query.enums import ChainEnum


class ConditionGroupABC(ABC):
    def __init__(self, chain: ChainEnum = ChainEnum.AND, not_: bool = False) -> None:
        self._chain = chain
        self._not = not_

    @property
    def chain(self) -> ChainEnum:
        return self._chain

    @property
    def not_(self) -> bool:
        return self._not

    @property
    @abstractmethod
    def conditions(self) -> list[Condition | ConditionGroupABC]: ...
