from __future__ import annotations


class DatabaseError(Exception):
    pass


class AdapterError(Exception):
    pass


class ConnectionLimitError(AdapterError):
    pass


class DriverError(Exception):
    pass


class QueryError(Exception):
    pass


class QueryWithParamsError(Exception):
    pass


class ModelError(Exception):
    pass
