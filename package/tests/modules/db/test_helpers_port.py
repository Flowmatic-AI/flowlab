from __future__ import annotations

from flowlab.modules.db import current_timestamp, escape_ansi, escape_backslash, now
from flowlab.modules.db.query.expressions import CurrentTimestamp


def test_escape_ansi_doubles_each_char() -> None:
    """Query::escapeAnsi doubles every occurrence of each char in `chars` (used e.g. by
    SQLServerDialect to escape '[' / ']' inside a quoted identifier). The hand-port used
    str.maketrans(chars, chars * 2), which raises ValueError for any non-empty input because
    the two maketrans arguments must have equal length."""
    assert escape_ansi("a[b]c", "[]") == "a[[b]]c"


def test_escape_ansi_single_char() -> None:
    assert escape_ansi("100%", "%") == "100%%"


def test_escape_ansi_empty_chars_is_noop() -> None:
    assert escape_ansi("hello", "") == "hello"


def test_escape_backslash_prepends_backslash() -> None:
    """Query::escapeBackslash prepends a backslash to every occurrence of each char in `chars`,
    and always escapes literal backslashes first. Used e.g. by ConditionsTrait::escapeLikeChars
    to escape LIKE wildcards. The hand-port used str.maketrans(chars, "\\\\" + chars), which
    raises ValueError for the same reason as escape_ansi."""
    assert escape_backslash("50%_off", "%_") == "50\\%\\_off"


def test_escape_backslash_escapes_existing_backslashes_first() -> None:
    assert escape_backslash("a\\b%c", "%") == "a\\\\b\\%c"


def test_now_returns_current_timestamp() -> None:
    """PHP's Query::now() returns `new DateTime()`, but this port deliberately diverges:
    commit bedc78b ("feat: now returns current_timestamp") makes now() an alias for
    currentTimestamp() so the SQL function is emitted instead of a client-side clock read.
    This test pins the intentional divergence."""
    assert isinstance(now(), CurrentTimestamp)


def test_current_timestamp_is_still_a_marker() -> None:
    assert isinstance(current_timestamp(), CurrentTimestamp)
