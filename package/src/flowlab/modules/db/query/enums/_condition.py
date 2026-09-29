from enum import StrEnum


class ConditionEnum(StrEnum):
    EQUALS = "="
    NOT_EQUALS = "<>"
    LESS_THAN = "<"
    LESS_THAN_OR_EQUALS = "<="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUALS = ">="
    BETWEEN = "BETWEEN"
    NOT_BETWEEN = "NOT BETWEEN"
    LIKE = "LIKE"
    NOT_LIKE = "NOT LIKE"
    GLOB = "GLOB"
    NOT_GLOB = "NOT GLOB"
    IN = "IN"
    NOT_IN = "NOT IN"
    REGEX = "REGEX"
    NOT_REGEX = "NOT REGEX"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT EXISTS"
    RAW = "RAW"
