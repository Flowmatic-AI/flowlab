from __future__ import annotations

from flowlab.modules.db.query import Condition, HavingGroup, WhereGroup
from flowlab.modules.db.query.enums import ChainEnum, ConditionEnum


def test_condition_creation() -> None:
    cond = Condition(
        condition=ConditionEnum.EQUALS,
        identifier="name",
        value="John",
        chain=ChainEnum.AND,
    )
    assert cond.condition == ConditionEnum.EQUALS
    assert cond.identifier == "name"
    assert cond.value == "John"
    assert cond.chain == ChainEnum.AND


def test_condition_default_chain() -> None:
    cond = Condition(condition=ConditionEnum.EQUALS, identifier="id", value=1)
    assert cond.chain == ChainEnum.AND


def test_where_group_creation() -> None:
    group = WhereGroup()
    assert group.chain == ChainEnum.AND
    assert group.not_ is False
    assert group.conditions == []


def test_where_group_with_not() -> None:
    group = WhereGroup(chain=ChainEnum.OR, not_=True)
    assert group.chain == ChainEnum.OR
    assert group.not_ is True


def test_where_group_add_condition() -> None:
    group = WhereGroup()
    cond = Condition(condition=ConditionEnum.EQUALS, identifier="name", value="John")
    group.add_condition(cond)
    assert len(group.conditions) == 1
    cond0 = group.conditions[0]
    assert isinstance(cond0, Condition)
    assert cond0.identifier == "name"


def test_having_group_creation() -> None:
    group = HavingGroup()
    assert group.chain == ChainEnum.AND
    assert group.not_ is False


def test_having_group_add_condition() -> None:
    group = HavingGroup()
    cond = Condition(condition=ConditionEnum.GREATER_THAN, identifier="count", value=5)
    group.add_condition(cond)
    assert len(group.conditions) == 1


def test_nested_groups() -> None:
    outer = WhereGroup()
    inner = WhereGroup(chain=ChainEnum.OR)
    inner.add_condition(Condition(condition=ConditionEnum.EQUALS, identifier="a", value=1))
    outer.add_condition(inner)
    assert len(outer.conditions) == 1
    assert isinstance(outer.conditions[0], WhereGroup)
