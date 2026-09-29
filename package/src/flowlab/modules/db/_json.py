from __future__ import annotations

import json
from datetime import date, datetime
from datetime import time as time_of_day
from decimal import Decimal
from typing import Any


def _encode_fallback(value: Any) -> Any:
    if isinstance(value, (datetime, date, time_of_day)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"object of type {type(value).__name__} is not JSON serializable")


def encode_json(value: Any) -> str:
    return json.dumps(value, default=_encode_fallback)


def decode_json(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
