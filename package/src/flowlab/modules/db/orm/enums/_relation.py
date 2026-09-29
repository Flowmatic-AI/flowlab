from enum import StrEnum


class RelationEnum(StrEnum):
    HAS_ONE = "has one"
    BELONGS_TO = "belongs to"
    HAS_MANY = "has many"
    MANY_TO_MANY = "many to many"
