from __future__ import annotations

import pytest

from flowlab.modules.db import QueryWithParams, QueryWithParamsError
from flowlab.modules.db._query_with_params import REGEX_PATTERN
from flowlab.modules.db.dialects import SQLDialect


def test_query_with_params_creation() -> None:
    qwp: QueryWithParams = QueryWithParams(query="SELECT * FROM t WHERE col = ?", params=[1])
    assert qwp.query == "SELECT * FROM t WHERE col = ?"
    assert qwp.params == [1]


def test_percent_s_to_question_marks() -> None:
    qwp: QueryWithParams = QueryWithParams(query="SELECT * FROM t WHERE col = %s", params=[1])
    result: QueryWithParams = qwp.percent_s_to_question_marks()
    assert result.query == "SELECT * FROM t WHERE col = ?"
    assert result.params == [1]


def test_percent_s_skips_single_quoted_strings() -> None:
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t WHERE col = %s AND name = '%s'",
        params=[1],
    )
    result: QueryWithParams = qwp.percent_s_to_question_marks()
    assert result.query == "SELECT * FROM t WHERE col = ? AND name = '%s'"


def test_percent_s_skips_double_quoted_strings() -> None:
    qwp: QueryWithParams = QueryWithParams(
        query='SELECT * FROM t WHERE col = %s AND name = "%s"',
        params=[1],
    )
    result: QueryWithParams = qwp.percent_s_to_question_marks()
    assert result.query == 'SELECT * FROM t WHERE col = ? AND name = "%s"'


def test_percent_s_skips_backtick_quoted_strings() -> None:
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t WHERE col = %s AND name = `%s`",
        params=[1],
    )
    result: QueryWithParams = qwp.percent_s_to_question_marks()
    assert result.query == "SELECT * FROM t WHERE col = ? AND name = `%s`"


def test_percent_s_multiple() -> None:
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t WHERE col1 = %s AND col2 = %s",
        params=[1, 2],
    )
    result: QueryWithParams = qwp.percent_s_to_question_marks()
    assert result.query == "SELECT * FROM t WHERE col1 = ? AND col2 = ?"


def test_percent_s_skips_line_comments() -> None:
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t -- %s stays in comment\nWHERE col = %s",
        params=[1],
    )
    result: QueryWithParams = qwp.percent_s_to_question_marks()
    assert result.query == "SELECT * FROM t -- %s stays in comment\nWHERE col = ?"


def test_percent_s_skips_block_comments() -> None:
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t /* %s stays in comment */ WHERE col = %s",
        params=[1],
    )
    result: QueryWithParams = qwp.percent_s_to_question_marks()
    assert result.query == "SELECT * FROM t /* %s stays in comment */ WHERE col = ?"


def test_percent_s_skips_hash_comments() -> None:
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t # %s stays in comment\nWHERE col = %s",
        params=[1],
    )
    result: QueryWithParams = qwp.percent_s_to_question_marks()
    assert result.query == "SELECT * FROM t # %s stays in comment\nWHERE col = ?"


def test_percent_s_skips_postgres_cast() -> None:
    """::cast syntax should not interfere with %s matching."""
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t WHERE col = %s AND col2::text = 'hello'",
        params=[1],
    )
    result: QueryWithParams = qwp.percent_s_to_question_marks()
    assert result.query == "SELECT * FROM t WHERE col = ? AND col2::text = 'hello'"


def test_percent_s_skips_question_marks() -> None:
    """? should remain as-is and %s should convert to ?."""
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t WHERE col = %s AND col2 = ?",
        params=[1, 2],
    )
    result: QueryWithParams = qwp.percent_s_to_question_marks()
    assert result.query == "SELECT * FROM t WHERE col = ? AND col2 = ?"


def test_to_sql_with_dialect() -> None:
    dialect: SQLDialect = SQLDialect()
    qwp: QueryWithParams = QueryWithParams(query="SELECT * FROM t WHERE col = ? AND col2 = ?", params=[1, "hello"])
    sql: str = qwp.to_sql(dialect)
    assert "1" in sql
    assert "'hello'" in sql


def test_to_sql_raises_when_params_run_short() -> None:
    """PHP's QueryWithParams::toSql throws QueryWithParamsException('question mark and param
    count do not match') when there are more placeholders than supplied params. The port must
    raise flowlab.modules.db._exceptions.QueryWithParamsError instead of silently leaving a literal '?'
    in the generated SQL."""
    dialect: SQLDialect = SQLDialect()
    qwp: QueryWithParams = QueryWithParams(query="SELECT * FROM t WHERE col = ? AND col2 = ?", params=[1])
    with pytest.raises(QueryWithParamsError):
        qwp.to_sql(dialect)


def test_to_sql_interpolates_values() -> None:
    dialect: SQLDialect = SQLDialect()
    qwp: QueryWithParams = QueryWithParams(query="SELECT * FROM t WHERE col = ?", params=[None])
    sql: str = qwp.to_sql(dialect)
    assert "NULL" in sql


def test_to_sql_respects_single_quoted_string_literals() -> None:
    dialect: SQLDialect = SQLDialect()
    qwp: QueryWithParams = QueryWithParams(query="SELECT '?', ?", params=[42])
    sql: str = qwp.to_sql(dialect)
    assert "'?'" in sql
    assert "42" in sql


def test_to_sql_respects_double_quoted_string_literals() -> None:
    dialect: SQLDialect = SQLDialect()
    qwp: QueryWithParams = QueryWithParams(query='SELECT "?", ?', params=[42])
    sql: str = qwp.to_sql(dialect)
    assert '"?"' in sql
    assert "42" in sql


def test_to_sql_respects_backtick_quoted_string_literals() -> None:
    dialect: SQLDialect = SQLDialect()
    qwp: QueryWithParams = QueryWithParams(query="SELECT `?`, ?", params=[42])
    sql: str = qwp.to_sql(dialect)
    assert "`?`" in sql
    assert "42" in sql


def test_to_sql_respects_line_comments() -> None:
    dialect: SQLDialect = SQLDialect()
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t -- comment\nWHERE col = ?",
        params=[42],
    )
    sql: str = qwp.to_sql(dialect)
    assert "42" in sql


def test_to_sql_respects_block_comments() -> None:
    dialect: SQLDialect = SQLDialect()
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t /* comment */ WHERE col = ?",
        params=[42],
    )
    sql: str = qwp.to_sql(dialect)
    assert "42" in sql


def test_to_sql_respects_percent_s_params() -> None:
    """%s should be interpolated in to_sql like ? placeholders."""
    dialect: SQLDialect = SQLDialect()
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t WHERE col = %s AND col2 = ?",
        params=[42, "hello"],
    )
    sql: str = qwp.to_sql(dialect)
    assert "42" in sql
    assert "'hello'" in sql
    assert "%s" not in sql


def test_regex_pattern_module_level() -> None:
    """REGEX_PATTERN is a compiled regex accessible at module level."""
    import re

    assert isinstance(REGEX_PATTERN, re.Pattern)


def test_question_marks_to_percent_s() -> None:
    """? should convert to %s."""
    qwp: QueryWithParams = QueryWithParams(query="SELECT * FROM t WHERE col = ?", params=[1])
    result: QueryWithParams = qwp.question_marks_to_percent_s()
    assert result.query == "SELECT * FROM t WHERE col = %s"
    assert result.params == [1]


def test_question_marks_skips_single_quoted_strings() -> None:
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t WHERE col = ? AND name = '?'",
        params=[1],
    )
    result: QueryWithParams = qwp.question_marks_to_percent_s()
    assert result.query == "SELECT * FROM t WHERE col = %s AND name = '?'"


def test_question_marks_skips_double_quoted_strings() -> None:
    qwp: QueryWithParams = QueryWithParams(
        query='SELECT * FROM t WHERE col = ? AND name = "?"',
        params=[1],
    )
    result: QueryWithParams = qwp.question_marks_to_percent_s()
    assert result.query == 'SELECT * FROM t WHERE col = %s AND name = "?"'


def test_question_marks_skips_backtick_quoted_strings() -> None:
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t WHERE col = ? AND name = `?`",
        params=[1],
    )
    result: QueryWithParams = qwp.question_marks_to_percent_s()
    assert result.query == "SELECT * FROM t WHERE col = %s AND name = `?`"


def test_question_marks_multiple() -> None:
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t WHERE col1 = ? AND col2 = ?",
        params=[1, 2],
    )
    result: QueryWithParams = qwp.question_marks_to_percent_s()
    assert result.query == "SELECT * FROM t WHERE col1 = %s AND col2 = %s"


def test_question_marks_skips_line_comments() -> None:
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t -- ? stays in comment\nWHERE col = ?",
        params=[1],
    )
    result: QueryWithParams = qwp.question_marks_to_percent_s()
    assert result.query == "SELECT * FROM t -- ? stays in comment\nWHERE col = %s"


def test_question_marks_skips_block_comments() -> None:
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t /* ? stays in comment */ WHERE col = ?",
        params=[1],
    )
    result: QueryWithParams = qwp.question_marks_to_percent_s()
    assert result.query == "SELECT * FROM t /* ? stays in comment */ WHERE col = %s"


def test_question_marks_skips_hash_comments() -> None:
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t # ? stays in comment\nWHERE col = ?",
        params=[1],
    )
    result: QueryWithParams = qwp.question_marks_to_percent_s()
    assert result.query == "SELECT * FROM t # ? stays in comment\nWHERE col = %s"


def test_question_marks_skips_percent_s() -> None:
    """%s should remain as-is and ? should convert to %s."""
    qwp: QueryWithParams = QueryWithParams(
        query="SELECT * FROM t WHERE col = ? AND col2 = %s",
        params=[1, 2],
    )
    result: QueryWithParams = qwp.question_marks_to_percent_s()
    assert result.query == "SELECT * FROM t WHERE col = %s AND col2 = %s"
