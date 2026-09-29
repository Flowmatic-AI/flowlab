from __future__ import annotations

from flowlab.modules.db import QueryWithParams
from flowlab.modules.db.dialects import MySQLDialect
from flowlab.modules.db.query import Condition, OnConflict
from flowlab.modules.db.query.ddl import AddColumn, AlterColumn, Column, DropConstraint, RenameColumn
from flowlab.modules.db.query.enums import ConditionEnum, TypeEnum
from flowlab.modules.db.query.expressions import CurrentTimestamp


def test_mysql_select(mysql_dialect: MySQLDialect) -> None:
    qwp: QueryWithParams = mysql_dialect.select(
        distinct=None,
        columns=["id", "name"],
        table="users",
        joins=None,
        where=None,
        group_by=None,
        having=None,
        order_by=None,
        limit=None,
        offset=None,
        unions=None,
    )
    assert qwp.query == "SELECT `id`, `name` FROM `users`"


def test_mysql_placeholder(mysql_dialect: MySQLDialect) -> None:
    """Verify MySQL uses ? placeholders, not %s."""
    qwp: QueryWithParams = mysql_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "Alice"}],
        on_conflict=None,
        returning=None,
        last_insert_id=None,
    )
    assert "?" in qwp.query
    assert "%s" not in qwp.query
    assert qwp.params == [1, "Alice"]


def test_mysql_on_duplicate_key_update(mysql_dialect: MySQLDialect) -> None:
    """Verify ON DUPLICATE KEY UPDATE with VALUES(col)."""
    from flowlab.modules.db.query.expressions import Values

    updates = {"name": Values()}
    qwp: QueryWithParams = mysql_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "John"}],
        on_conflict=OnConflict(conflict=["id"], updates=updates),
        returning=None,
        last_insert_id=None,
    )
    assert "ON DUPLICATE KEY UPDATE" in qwp.query
    assert "VALUES(`name`)" in qwp.query


def test_mysql_on_duplicate_key_update_all(mysql_dialect: MySQLDialect) -> None:
    """Empty updates dict = update all columns from VALUES."""
    qwp: QueryWithParams = mysql_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "John", "email": "john@example.com"}],
        on_conflict=OnConflict(conflict=["id"], updates={}),
        returning=None,
        last_insert_id=None,
    )
    assert "ON DUPLICATE KEY UPDATE" in qwp.query
    assert "VALUES(`id`)" in qwp.query
    assert "VALUES(`name`)" in qwp.query
    assert "VALUES(`email`)" in qwp.query


def test_mysql_on_duplicate_key_update_specific(mysql_dialect: MySQLDialect) -> None:
    """Specific column updates with literal values."""
    updates = {"name": "UpdatedName", "count": 42}
    qwp: QueryWithParams = mysql_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "John", "count": 0}],
        on_conflict=OnConflict(conflict=["id"], updates=updates),
        returning=None,
        last_insert_id=None,
    )
    assert "ON DUPLICATE KEY UPDATE" in qwp.query
    assert "`name` = ?" in qwp.query
    assert "`count` = ?" in qwp.query
    assert qwp.params == [1, "John", 0, "UpdatedName", 42]


def test_mysql_on_duplicate_key_update_do_nothing_uses_insert_ignore(
    mysql_dialect: MySQLDialect,
) -> None:
    """DO NOTHING should produce INSERT IGNORE instead of raising."""
    qwp = mysql_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "John"}],
        on_conflict=OnConflict(conflict=["id"], updates=None),
        returning=None,
        last_insert_id=None,
    )
    assert qwp.query.startswith("INSERT IGNORE INTO ")
    assert "ON DUPLICATE KEY UPDATE" not in qwp.query


def test_mysql_on_duplicate_key_update_last_insert_id_all(
    mysql_dialect: MySQLDialect,
) -> None:
    """last_insert_id with update-all should prepend LAST_INSERT_ID(id) and skip id from VALUES."""
    qwp: QueryWithParams = mysql_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "John", "email": "john@example.com"}],
        on_conflict=OnConflict(conflict=["id"], updates={}),
        returning=None,
        last_insert_id="id",
    )
    assert "`id` = LAST_INSERT_ID(`id`)" in qwp.query
    assert "VALUES(`id`)" not in qwp.query
    assert "VALUES(`name`)" in qwp.query
    assert "VALUES(`email`)" in qwp.query
    update_part = qwp.query.split("ON DUPLICATE KEY UPDATE ")[1]
    assert update_part.startswith("`id` = LAST_INSERT_ID(`id`)")


def test_mysql_on_duplicate_key_update_last_insert_id_specific(
    mysql_dialect: MySQLDialect,
) -> None:
    """last_insert_id with specific updates appends its own clause: this
    mirrors PHP's plain array-key assignment ($updates[$lastInsertId] = ...),
    which only preserves a column's original position when it already
    existed in on_conflict.updates. Here 'id' is new, so it is appended
    *after* the caller-supplied 'name' update, not prepended."""
    updates = {"name": "UpdatedName"}
    qwp: QueryWithParams = mysql_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "John"}],
        on_conflict=OnConflict(conflict=["id"], updates=updates),
        returning=None,
        last_insert_id="id",
    )
    assert "`id` = LAST_INSERT_ID(`id`)" in qwp.query
    assert "`name` = ?" in qwp.query
    update_part = qwp.query.split("ON DUPLICATE KEY UPDATE ")[1]
    assert update_part.startswith("`name` = ?")
    assert update_part.endswith("`id` = LAST_INSERT_ID(`id`)")


def test_mysql_on_duplicate_key_update_do_nothing_with_last_insert_id(
    mysql_dialect: MySQLDialect,
) -> None:
    """DO NOTHING (updates=None) combined with a last_insert_id should NOT
    become INSERT IGNORE -- MySQLDialect::buildOnConflict only takes the
    INSERT IGNORE shortcut when no last_insert_id was requested; otherwise it
    falls through to ON DUPLICATE KEY UPDATE so LAST_INSERT_ID() reflects the
    pre-existing row."""
    qwp: QueryWithParams = mysql_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "John"}],
        on_conflict=OnConflict(conflict=["id"], updates=None),
        returning=None,
        last_insert_id="id",
    )
    assert not qwp.query.startswith("INSERT IGNORE")
    assert "ON DUPLICATE KEY UPDATE `id` = LAST_INSERT_ID(`id`)" in qwp.query


def test_mysql_no_returning_is_silently_dropped(mysql_dialect: MySQLDialect) -> None:
    """MySQL has no native RETURNING support; MySQLDialect::buildReturning
    (via the base) is a silent no-op, never a raise."""
    qwp = mysql_dialect.insert(
        table="users",
        values=[{"name": "John"}],
        on_conflict=None,
        returning=["id"],
        last_insert_id=None,
    )
    assert "RETURNING" not in qwp.query


def test_mysql_returning_skipped_on_update_even_when_mariadb_supports_it() -> None:
    """MySQLDialect::buildReturning always skips RETURNING for UPDATE
    queries specifically, even on a MariaDB version that otherwise supports
    it (an INSERT on the very same dialect instance still gets RETURNING)."""
    mariadb = MySQLDialect(version="10.5.0", is_mariadb=True)
    assert mariadb.returning is True

    update_qwp = mariadb.update(
        table="users",
        updates={"name": "Jane"},
        where=None,
        returning=["id"],
    )
    assert "RETURNING" not in update_qwp.query

    insert_qwp = mariadb.insert(
        table="users",
        values=[{"name": "Jane"}],
        on_conflict=None,
        returning=["id"],
        last_insert_id=None,
    )
    assert "RETURNING" in insert_qwp.query


def test_mysql_on_conflict_gating_matches_mariadb_vs_mysql(mysql_dialect: MySQLDialect) -> None:
    """MySQLDialect::onConflict(): MariaDB is always true; plain MySQL is
    gated on version >= 4.1."""
    assert mysql_dialect.on_conflict is True

    old_mysql = MySQLDialect(version="4.0.0")
    assert old_mysql.on_conflict is False

    old_mariadb = MySQLDialect(version="4.0.0", is_mariadb=True)
    assert old_mariadb.on_conflict is True


def test_mysql_lateral_excludes_mariadb() -> None:
    """MySQLDialect::lateral() requires the MySQL driver specifically, not
    MariaDB, even past the 8.0.14 version threshold."""
    mariadb = MySQLDialect(version="8.0.14", is_mariadb=True)
    assert mariadb.lateral is False

    mysql = MySQLDialect(version="8.0.14", is_mariadb=False)
    assert mysql.lateral is True


def test_mysql_type_mapping(mysql_dialect: MySQLDialect) -> None:
    assert mysql_dialect.type(TypeEnum.BOOL) == "TINYINT"
    assert mysql_dialect.type(TypeEnum.INT) == "INTEGER"
    assert mysql_dialect.type(TypeEnum.INT, 64) == "BIGINT"
    assert mysql_dialect.type(TypeEnum.FLOAT) == "FLOAT"
    assert mysql_dialect.type(TypeEnum.FLOAT, 64) == "DOUBLE"
    assert mysql_dialect.type(TypeEnum.STRING) == "VARCHAR(255)"
    assert mysql_dialect.type(TypeEnum.STRING, 64) == "VARCHAR(64)"
    assert mysql_dialect.type(TypeEnum.STRING, 65536) == "MEDIUMTEXT"
    assert mysql_dialect.type(TypeEnum.STRING, 16777216) == "LONGTEXT"
    assert mysql_dialect.type(TypeEnum.DATETIME) == "DATETIME"
    assert mysql_dialect.type(TypeEnum.DATETIME, 6) == "DATETIME(6)"


def test_mysql_type_datetime_clamps_fractional_seconds_precision(mysql_dialect: MySQLDialect) -> None:
    """Reviewed deviation from MySQLDialect.php:237: MySQL's fractional-
    seconds precision (fsp) is only valid in 0-6, but callers pass
    bit-width sizes elsewhere in this API (e.g. 32, 64). A faithful port
    of the PHP `sprintf('DATETIME(%d)', $size)` would emit invalid SQL like
    DATETIME(64); size is clamped to MySQL's real maximum of 6 instead."""
    assert mysql_dialect.type(TypeEnum.DATETIME, None) == "DATETIME"
    assert mysql_dialect.type(TypeEnum.DATETIME, 0) == "DATETIME"
    assert mysql_dialect.type(TypeEnum.DATETIME, 6) == "DATETIME(6)"
    assert mysql_dialect.type(TypeEnum.DATETIME, 7) == "DATETIME(6)"
    assert mysql_dialect.type(TypeEnum.DATETIME, 64) == "DATETIME(6)"


def test_mysql_current_timestamp_default_matches_column_precision(
    mysql_dialect: MySQLDialect,
) -> None:
    """Reviewed deviation from MySQLDialect.php: MySQL rejects a bare
    DEFAULT CURRENT_TIMESTAMP (and its synonym NOW()) on a DATETIME/TIMESTAMP
    column with a fractional seconds part -- `DATETIME(6) DEFAULT
    CURRENT_TIMESTAMP` raises error 1067 "Invalid default value". The default's
    fsp is matched to the column's instead."""
    col = Column(name="updated_at", type=TypeEnum.DATETIME, size=6, default=CurrentTimestamp())
    assert mysql_dialect._build_column(col) == "`updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6)"

    col = Column(name="updated_at", type="TIMESTAMP(3)", default=CurrentTimestamp())
    assert mysql_dialect._build_column(col) == "`updated_at` TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3)"


def test_mysql_current_timestamp_default_left_alone_without_precision(
    mysql_dialect: MySQLDialect,
) -> None:
    """A column with no fsp takes the bare form -- CURRENT_TIMESTAMP(0) is
    legal but needlessly noisy, and the PHP output is what callers expect."""
    col = Column(name="created_at", type=TypeEnum.DATETIME, default=CurrentTimestamp())
    assert mysql_dialect._build_column(col) == "`created_at` DATETIME DEFAULT CURRENT_TIMESTAMP"

    col = Column(name="created_at", type=TypeEnum.STRING, size=6, default=CurrentTimestamp())
    assert mysql_dialect._build_column(col) == "`created_at` VARCHAR(6) DEFAULT CURRENT_TIMESTAMP"


def test_mysql_bool_casting(mysql_dialect: MySQLDialect) -> None:
    """PHP doesn't override castBool/parseBool for MySQL at all -- these all
    come from the base implementation."""
    assert mysql_dialect.cast_bool(True) == 1
    assert mysql_dialect.cast_bool(False) == 0
    assert mysql_dialect.parse_bool(True) is True
    assert mysql_dialect.parse_bool(False) is False
    assert mysql_dialect.parse_bool(1) is True
    assert mysql_dialect.parse_bool(0) is False
    assert mysql_dialect.parse_bool("true") is True
    assert mysql_dialect.parse_bool("false") is False
    assert mysql_dialect.parse_bool("1") is True
    assert mysql_dialect.parse_bool("yes") is True


def test_mysql_auto_increment_column(mysql_dialect: MySQLDialect) -> None:
    """_build_column() alone only adds AUTO_INCREMENT -- MySQLDialect never
    adds PRIMARY KEY itself; that comes from create_table() folding the
    auto-increment column into the primary key list instead."""
    col = Column(name="id", type=TypeEnum.INT, auto_increment=True)
    col_def: str = mysql_dialect._build_column(col)
    assert "AUTO_INCREMENT" in col_def
    assert "PRIMARY KEY" not in col_def


def test_mysql_auto_increment_column_not_null_and_default_preserved(
    mysql_dialect: MySQLDialect,
) -> None:
    """The old _build_column() early-returned for auto_increment columns,
    silently dropping NOT NULL/DEFAULT. MySQLDialect::buildColumn appends
    AUTO_INCREMENT *after* calling parent::buildColumn(), so those fragments
    must still be present."""
    col = Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True)
    col_def: str = mysql_dialect._build_column(col)
    assert col_def == "`id` INTEGER NOT NULL AUTO_INCREMENT"


def test_mysql_auto_increment_column_drops_default(mysql_dialect: MySQLDialect) -> None:
    """MySQL rejects a DEFAULT on an AUTO_INCREMENT column with error 1067, so
    the base builder drops it."""
    col = Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True, default=5)
    assert mysql_dialect._build_column(col) == "`id` INTEGER NOT NULL AUTO_INCREMENT"


def test_mysql_create_table_auto_increment_adds_primary_key(
    mysql_dialect: MySQLDialect,
) -> None:
    """MySQLDialect::createTable folds auto-increment columns into the
    primary key list even when add_primary_key was not explicitly
    requested (primary_keys=None here)."""
    qwp: QueryWithParams = mysql_dialect.create_table(
        if_not_exists=False,
        table="users",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True),
            Column(name="other_pk", type=TypeEnum.INT),
        ],
        primary_keys=["other_pk"],
    )
    assert "PRIMARY KEY (`other_pk`, `id`)" in qwp.query


def test_mysql_regex_condition_uses_function_form_on_mysql8(mysql_dialect: MySQLDialect) -> None:
    """MySQLDialect::buildConditionRegex: plain MySQL >= 8.0 uses the shared
    regexp_like() function form, not the REGEXP operator."""
    cond = Condition(
        condition=ConditionEnum.REGEX,
        identifier="email",
        value="^[a-z]+@example\\.com$",
    )
    parts: list[str] = []
    params: list[object] = []
    mysql_dialect._build_condition(parts, params, cond)
    result = "".join(parts)
    assert result.startswith("regexp_like(`email`, ")
    assert "REGEXP" not in result


def test_mysql_not_regex_condition_uses_function_form_on_mysql8(mysql_dialect: MySQLDialect) -> None:
    cond = Condition(
        condition=ConditionEnum.NOT_REGEX,
        identifier="email",
        value="^spam@",
    )
    parts: list[str] = []
    params: list[object] = []
    mysql_dialect._build_condition(parts, params, cond)
    result = "".join(parts)
    assert result == "NOT regexp_like(`email`, ?, ?)"


def test_mysql_regex_condition_uses_operator_form_on_mariadb() -> None:
    """MySQLDialect::buildConditionRegex: MariaDB always uses the
    REGEXP/NOT REGEXP operator, regardless of version."""
    mariadb = MySQLDialect(version="10.5.0", is_mariadb=True)
    cond = Condition(condition=ConditionEnum.REGEX, identifier="email", value="^a@b$")
    parts: list[str] = []
    params: list[object] = []
    mariadb._build_condition(parts, params, cond)
    result = "".join(parts)
    assert result == "`email` REGEXP ?"

    not_cond = Condition(condition=ConditionEnum.NOT_REGEX, identifier="email", value="^a@b$")
    parts2: list[str] = []
    params2: list[object] = []
    mariadb._build_condition(parts2, params2, not_cond)
    assert "".join(parts2) == "`email` NOT REGEXP ?"


def test_mysql_regex_condition_operator_form_via_option(mysql_dialect: MySQLDialect) -> None:
    """The use_regexp option forces the operator form even on MySQL 8+."""
    mysql = MySQLDialect(version="8.0.0", options={"use_regexp": True})
    cond = Condition(condition=ConditionEnum.REGEX, identifier="email", value="^a@b$")
    parts: list[str] = []
    params: list[object] = []
    mysql._build_condition(parts, params, cond)
    assert "".join(parts) == "`email` REGEXP ?"


def test_mysql_like_condition_case_sensitive_uses_binary(mysql_dialect: MySQLDialect) -> None:
    """MySQLDialect::buildConditionLike: the default (case_insensitive=False)
    request needs LIKE BINARY to force a byte-wise, collation-independent
    comparison; case_insensitive=True can use plain LIKE."""
    cond = Condition(condition=ConditionEnum.LIKE, identifier="name", value="%john%")
    parts: list[str] = []
    params: list[object] = []
    mysql_dialect._build_condition(parts, params, cond)
    assert "".join(parts) == "`name` LIKE BINARY ?"

    ci_cond = Condition(condition=ConditionEnum.LIKE, identifier="name", value="%john%", case_insensitive=True)
    parts2: list[str] = []
    params2: list[object] = []
    mysql_dialect._build_condition(parts2, params2, ci_cond)
    assert "".join(parts2) == "`name` LIKE ?"

    not_cond = Condition(condition=ConditionEnum.NOT_LIKE, identifier="name", value="%john%")
    parts3: list[str] = []
    params3: list[object] = []
    mysql_dialect._build_condition(parts3, params3, not_cond)
    assert "".join(parts3) == "`name` NOT LIKE BINARY ?"


def test_mysql_no_distinct_on(mysql_dialect: MySQLDialect) -> None:
    assert not mysql_dialect.distinct_on


def test_mysql_escape_identifier(mysql_dialect: MySQLDialect) -> None:
    assert mysql_dialect.escape_identifier("users") == "`users`"
    assert mysql_dialect.escape_identifier("order") == "`order`"
    assert mysql_dialect.escape_identifier("select") == "`select`"


def test_mysql_escape_string(mysql_dialect: MySQLDialect) -> None:
    """MySQLDialect::ESCAPE_STRING is '"' (double quote), and ESCAPE_CHARS
    backslash-escapes control characters as well as the quote itself --
    unlike the ANSI base, which doubles the wrapping quote and only strips
    NUL bytes."""
    assert mysql_dialect.escape_string("it's") == '"it\\\'s"'
    assert mysql_dialect.escape_string("back\\slash") == '"back\\\\slash"'
    assert mysql_dialect.escape_string("normal") == '"normal"'
    assert mysql_dialect.escape_string("line1\nline2\ttab\r\x00\x1a") == ('"line1\\nline2\\ttab\\r\\0\\Z"')


def test_mysql_transaction_syntax(mysql_dialect: MySQLDialect) -> None:
    assert mysql_dialect.begin_transaction().query == "START TRANSACTION"
    assert mysql_dialect.commit_transaction().query == "COMMIT"
    assert mysql_dialect.rollback_transaction().query == "ROLLBACK"


def test_mysql_create_table(mysql_dialect: MySQLDialect) -> None:
    qwp: QueryWithParams = mysql_dialect.create_table(
        if_not_exists=True,
        table="users",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True),
            Column(name="name", type=TypeEnum.STRING, size=100, not_null=True),
            Column(name="email", type=TypeEnum.STRING, size=255),
        ],
    )
    query = qwp.query
    assert "CREATE TABLE IF NOT EXISTS" in query
    assert "`users`" in query
    assert "`id`" in query
    assert "AUTO_INCREMENT" in query
    assert "PRIMARY KEY" in query
    assert "`name`" in query
    assert "VARCHAR(100)" in query
    assert "NOT NULL" in query
    assert "`email`" in query
    assert "VARCHAR(255)" in query


def test_mysql_alter_add_column(mysql_dialect: MySQLDialect) -> None:
    qwp: QueryWithParams = mysql_dialect._build_alter(
        "users",
        AddColumn(name="age", type=TypeEnum.INT, not_null=True),
    )
    assert qwp.query == "ALTER TABLE `users` ADD COLUMN `age` INTEGER NOT NULL"


def test_mysql_alter_rename_column(mysql_dialect: MySQLDialect) -> None:
    qwp: QueryWithParams = mysql_dialect._build_alter(
        "users",
        RenameColumn(old_name="name", new_name="username"),
    )
    assert qwp.query == "ALTER TABLE `users` RENAME COLUMN `name` TO `username`"


def test_mysql_alter_drop_constraint_always_uses_drop_index(mysql_dialect: MySQLDialect) -> None:
    """MySQLDialect::buildAlterTableDropConstraint always rewrites
    'DROP CONSTRAINT name' to 'DROP INDEX name', regardless of what kind of
    constraint it was -- the AltersMixin.drop_constraint() API (mirroring
    PHP's AltersTrait::dropConstraint()) only ever carries a bare name, no
    constraint-kind discriminator."""
    qwp: QueryWithParams = mysql_dialect._build_alter(
        "orders",
        DropConstraint(name="fk_user_id"),
    )
    assert qwp.query == "ALTER TABLE `orders` DROP INDEX `fk_user_id`"


def test_mysql_insert_with_params(mysql_dialect: MySQLDialect) -> None:
    """Verify INSERT generates ? placeholders and correct params."""
    qwp: QueryWithParams = mysql_dialect.insert(
        table="users",
        values=[
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ],
        on_conflict=None,
        returning=None,
        last_insert_id=None,
    )
    assert qwp.query == ("INSERT INTO `users` (`name`, `age`) VALUES (?, ?), (?, ?)")
    assert qwp.params == ["Alice", 30, "Bob", 25]


def test_mysql_update_with_params(mysql_dialect: MySQLDialect) -> None:
    """Verify UPDATE generates ? placeholders."""
    from flowlab.modules.db.query import Condition
    from flowlab.modules.db.query.enums import ConditionEnum

    where = [
        Condition(condition=ConditionEnum.EQUALS, identifier="id", value=42),
    ]
    qwp: QueryWithParams = mysql_dialect.update(
        table="users",
        updates={"name": "UpdatedName", "age": 35},
        where=where,
        returning=None,
    )
    assert "UPDATE `users` SET `name` = ?, `age` = ?" in qwp.query
    assert "WHERE `id` = ?" in qwp.query
    assert qwp.params == ["UpdatedName", 35, 42]


def test_mysql_delete_with_params(mysql_dialect: MySQLDialect) -> None:
    """Verify DELETE generates ? placeholders."""
    from flowlab.modules.db.query import Condition
    from flowlab.modules.db.query.enums import ConditionEnum

    where = [
        Condition(condition=ConditionEnum.EQUALS, identifier="id", value=99),
    ]
    qwp: QueryWithParams = mysql_dialect.delete(
        table="users",
        where=where,
        returning=None,
    )
    assert "DELETE FROM `users`" in qwp.query
    assert "WHERE `id` = ?" in qwp.query
    assert qwp.params == [99]


def test_mysql_drop_table(mysql_dialect: MySQLDialect) -> None:
    qwp: QueryWithParams = mysql_dialect.drop_table(
        if_exists=True,
        table="users",
    )
    assert qwp.query == "DROP TABLE IF EXISTS `users`"

    qwp2: QueryWithParams = mysql_dialect.drop_table(
        if_exists=False,
        table="users",
    )
    assert qwp2.query == "DROP TABLE `users`"


def test_mysql_version_gating(mysql_dialect: MySQLDialect) -> None:
    assert mysql_dialect.distinct_on is False
    assert mysql_dialect.lateral is False
    assert mysql_dialect.on_conflict is True
    assert mysql_dialect.returning is False
    assert mysql_dialect.savepoints is True

    mysql_8014 = MySQLDialect(version="8.0.14")
    assert mysql_8014.lateral is True

    mysql_8020 = MySQLDialect(version="8.0.20")
    assert mysql_8020.lateral is True


def test_mysql_alter_column_raw_sql_uses_modify(mysql_dialect: MySQLDialect) -> None:
    qwps: list[QueryWithParams] = mysql_dialect.alter_table(
        "articles",
        [AlterColumn(column="title", sql="VARCHAR(50) NOT NULL")],
    )
    assert [q.query for q in qwps] == ["ALTER TABLE `articles` MODIFY COLUMN `title` VARCHAR(50) NOT NULL"]
