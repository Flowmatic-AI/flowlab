from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from flowlab.modules.db._exceptions import QueryWithParamsError

if TYPE_CHECKING:
    from flowlab.modules.db.dialects import DialectABC

REGEX_PATTERN = re.compile(
    r"""(?x)
    (?:
        '(?:\\.|[^\\'])*'
        |"(?:\\.|[^\\"])*"
        |`(?:\\.|[^\\`])*`
        |\[(?:\\.|[^\[\]])*?\]
        |--[^\r\n]*
        |/\*[\s\S]*?\*/
        |\#.*
    )
    |
    (\?)
    |
    ((?<!%)%s)
    """,
    re.MULTILINE,
)


@dataclass
class QueryWithParams:
    query: str
    params: list[Any] = field(default_factory=list)

    def percent_s_to_question_marks(self) -> QueryWithParams:
        def _replacer(match: re.Match[str]) -> str:
            if match.group(2) is not None:
                return "?"
            return match.group(0)

        query = REGEX_PATTERN.sub(_replacer, self.query)
        return QueryWithParams(query=query, params=list(self.params))

    def question_marks_to_percent_s(self) -> QueryWithParams:
        def _replacer(match: re.Match[str]) -> str:
            if match.group(1) is not None:
                return "%s"
            return match.group(0)

        query = REGEX_PATTERN.sub(_replacer, self.query)
        return QueryWithParams(query=query, params=list(self.params))

    def to_sql(self, dialect: DialectABC) -> str:
        param_idx = 0

        def _replacer(match: re.Match[str]) -> str:
            nonlocal param_idx
            if match.group(1) is not None or match.group(2) is not None:
                if param_idx >= len(self.params):
                    raise QueryWithParamsError("placeholder and param count do not match")
                value = self.params[param_idx]
                casted = dialect.cast_to_query(value)
                param_idx += 1
                return casted
            return match.group(0)

        return REGEX_PATTERN.sub(_replacer, self.query)
