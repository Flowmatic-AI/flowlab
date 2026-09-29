import re
from dataclasses import dataclass
from typing import Self

UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}

_PATTERN = re.compile(r"^(\d+)\s*/\s*(\d+)?\s*([a-z]+?)s?$")


@dataclass(frozen=True)
class Limit:
    """``attempts`` per window of ``seconds``, written ``"5/minute"``, ``"100/hour"`` or ``"10/5 minutes"``."""

    attempts: int
    seconds: int

    def __post_init__(self) -> None:
        if self.attempts < 1 or self.seconds < 1:
            raise ValueError("a rate limit needs at least 1 attempt per window of at least 1 second")

    @classmethod
    def parse(cls, value: "str | Limit") -> Self:
        if isinstance(value, cls):
            return value

        if isinstance(value, Limit):
            return cls(value.attempts, value.seconds)

        match = _PATTERN.match(value.strip().lower())

        if match is None or match[3] not in UNITS:
            raise ValueError(
                f"invalid rate limit {value!r}: expected '<attempts>/<unit>', like '5/minute' or '10/5 minutes'"
            )

        return cls(int(match[1]), int(match[2] or 1) * UNITS[match[3]])

    def __str__(self) -> str:
        for unit, seconds in reversed(UNITS.items()):
            if self.seconds % seconds == 0:
                count = self.seconds // seconds
                return f"{self.attempts}/{unit}" if count == 1 else f"{self.attempts}/{count} {unit}s"

        raise AssertionError("unreachable: every window is a whole number of seconds")
