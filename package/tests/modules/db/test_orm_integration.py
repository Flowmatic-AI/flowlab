"""Cross-engine integration tests for the ORM.

Every test runs against SQLite, PostgreSQL and MySQL. SQLite uses an in-memory
database and always runs; the other two are skipped when their server is not
reachable, so the suite stays green without them. Bring both up with::

    docker compose up -d
"""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest

from flowlab.modules.db.database import DB, DatabaseABC
from flowlab.modules.db.orm import (
    AutoIncrement,
    BelongsTo,
    HasMany,
    HasOne,
    ManyToMany,
    Model,
    PrimaryKey,
    belongs_to,
    has_many,
    has_one,
    many_to_many,
)

PG_HOST: str = "localhost"
PG_PORT: int = 5432
PG_DBNAME: str = "postgres"
PG_USER: str = "postgres"

MYSQL_HOST: str = "localhost"
MYSQL_PORT: int = 3306
MYSQL_USER: str = "root"
MYSQL_PASSWORD: str = ""
MYSQL_DATABASE: str = "flowlab_test"

TABLES: list[str] = [
    "orm_post_tags",
    "orm_comments",
    "orm_posts",
    "orm_profiles",
    "orm_tags",
    "orm_users",
    "orm_countries",
]


class OrmCountry(Model):
    __table__ = "orm_countries"

    code: PrimaryKey[str]
    name: str


class OrmProfile(Model):
    __table__ = "orm_profiles"

    id: AutoIncrement = None
    user_id: int
    bio: str


class OrmComment(Model):
    __table__ = "orm_comments"

    id: AutoIncrement = None
    post_id: int
    body: str


class OrmTag(Model):
    __table__ = "orm_tags"

    id: AutoIncrement = None
    slug: str


class OrmPost(Model):
    __table__ = "orm_posts"

    id: AutoIncrement = None
    user_id: int
    title: str

    author: BelongsTo[OrmUser] = belongs_to(foreign_key="user_id")
    comments: HasMany[OrmComment] = has_many(foreign_key="post_id")
    tags: ManyToMany[OrmTag] = many_to_many(
        "orm_post_tags", through_primary_key="post_id", through_foreign_key="tag_id"
    )


class OrmUser(Model):
    __table__ = "orm_users"

    id: AutoIncrement = None
    name: str
    country_code: str | None = None

    country: BelongsTo[OrmCountry] = belongs_to(foreign_key="country_code")
    profile: HasOne[OrmProfile] = has_one(foreign_key="user_id")
    posts: HasMany[OrmPost] = has_many(foreign_key="user_id")


def _port_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)

    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def _mysql_database() -> bool:
    try:
        import mysql.connector
    except ImportError:
        return False

    try:
        connection = mysql.connector.connect(
            host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD, database="mysql"
        )
    except mysql.connector.Error:
        return False

    try:
        cursor = connection.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}`")
        connection.commit()
        cursor.close()
    finally:
        connection.close()

    return True


def _create_schema(db: DatabaseABC) -> None:
    for table in TABLES:
        db.drop_table(table).if_exists().execute()

    db.create_table("orm_countries").string("code", size=64, not_null=True).string("name").primary_keys(
        ["code"]
    ).execute()
    db.create_table("orm_users").identity("id").string("name", not_null=True).string("country_code", size=64).execute()
    db.create_table("orm_profiles").identity("id").integer("user_id").text("bio").execute()
    db.create_table("orm_posts").identity("id").integer("user_id").string("title", not_null=True).execute()
    db.create_table("orm_comments").identity("id").integer("post_id").text("body").execute()
    db.create_table("orm_tags").identity("id").string("slug", not_null=True).execute()
    db.create_table("orm_post_tags").integer("post_id").integer("tag_id").execute()


@pytest.fixture(params=["sqlite", "postgres", "mysql"])
def orm_db(request: pytest.FixtureRequest) -> Iterator[DatabaseABC]:
    """Yield a database with the ORM schema in place, once per engine."""
    engine: str = request.param

    if engine == "sqlite":
        db: DatabaseABC = DB.connect_sqlite(":memory:")
    elif engine == "postgres":
        if not _port_reachable(PG_HOST, PG_PORT):
            pytest.skip("PostgreSQL is not reachable on localhost:5432")

        db = DB.connect_postgresql(PG_DBNAME, host=PG_HOST, port=PG_PORT, user=PG_USER, asyncpg_adapter=False)
    else:
        if not _port_reachable(MYSQL_HOST, MYSQL_PORT) or not _mysql_database():
            pytest.skip("MySQL is not reachable on localhost:3306")

        db = DB.connect_mysql(
            MYSQL_DATABASE, host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD
        )

    _create_schema(db)

    try:
        yield db
    finally:
        for table in TABLES:
            db.drop_table(table).if_exists().execute()

        db.close()


def _seed(db: DatabaseABC) -> OrmUser:
    db.insert_models([OrmCountry(code="nl", name="Netherlands"), OrmCountry(code="be", name="Belgium")]).execute()

    shared = OrmTag(slug="sql")
    user = OrmUser(
        name="Alice",
        country_code="nl",
        profile=OrmProfile(user_id=0, bio="writes about databases"),
        posts=[
            OrmPost(
                user_id=0,
                title="A1",
                comments=[OrmComment(post_id=0, body="c1"), OrmComment(post_id=0, body="c2")],
                tags=[shared, OrmTag(slug="beginner")],
            ),
            OrmPost(user_id=0, title="A2", tags=[shared]),
        ],
    )

    db.insert_model(user).relation("profile").relation("posts.comments").relation("posts.tags").execute()

    return user


def test_insert_cascade_fills_keys_on_every_engine(orm_db: DatabaseABC) -> None:
    """The generated primary key propagates to children and grandchildren."""
    user = _seed(orm_db)

    assert user.id is not None
    assert [post.user_id for post in user.posts] == [user.id, user.id]
    assert [comment.post_id for comment in user.posts[0].comments] == [user.posts[0].id] * 2
    assert all(post.id is not None for post in user.posts)
    assert all(tag.id is not None for post in user.posts for tag in post.tags)


def test_insert_shares_one_row_for_a_shared_related_instance(orm_db: DatabaseABC) -> None:
    """A model instance reused across parents is inserted once and linked twice."""
    user = _seed(orm_db)

    tag_ids = {tag.id for post in user.posts for tag in post.tags}

    assert len(tag_ids) == 2
    assert orm_db.select("orm_tags").count() == 2
    assert orm_db.select("orm_post_tags").count() == 3


def test_has_one_and_belongs_to_load(orm_db: DatabaseABC) -> None:
    _seed(orm_db)

    user = orm_db.select_models(OrmUser).relation("profile").relation("country").fetch_model()

    assert user is not None
    assert user.profile is not None
    assert user.profile.bio == "writes about databases"
    assert user.country is not None
    assert user.country.name == "Netherlands"


def test_has_many_and_many_to_many_load(orm_db: DatabaseABC) -> None:
    _seed(orm_db)

    user = orm_db.select_models(OrmUser).relation("posts.comments").relation("posts.tags").fetch_model()

    assert user is not None
    assert [post.title for post in user.posts] == ["A1", "A2"]
    assert [comment.body for comment in user.posts[0].comments] == ["c1", "c2"]
    assert sorted(tag.slug for tag in user.posts[0].tags) == ["beginner", "sql"]
    assert [tag.slug for tag in user.posts[1].tags] == ["sql"]
    assert user.posts[1].comments == []


def test_belongs_to_shares_one_instance_between_parents(orm_db: DatabaseABC) -> None:
    _seed(orm_db)

    posts = orm_db.select_models(OrmPost).relation("author").order_by_asc("id").fetch_models()

    assert len(posts) == 2
    assert posts[0].author is not None
    assert posts[0].author.name == "Alice"
    assert posts[0].author is posts[1].author


def test_relation_with_no_matching_rows_stays_empty(orm_db: DatabaseABC) -> None:
    orm_db.insert_model(OrmUser(name="Loner")).execute()

    user = orm_db.select_models(OrmUser).relation("posts").relation("profile").relation("country").fetch_model()

    assert user is not None
    assert user.posts == []
    assert user.profile is None
    assert user.country is None


def test_customize_callback_orders_a_relation(orm_db: DatabaseABC) -> None:
    _seed(orm_db)

    ascending = orm_db.select_models(OrmUser).relation("posts", lambda query: query.order_by_asc("title")).fetch_model()
    descending = (
        orm_db.select_models(OrmUser).relation("posts", lambda query: query.order_by_desc("title")).fetch_model()
    )

    assert ascending is not None
    assert descending is not None
    assert [post.title for post in ascending.posts] == ["A1", "A2"]
    assert [post.title for post in descending.posts] == ["A2", "A1"]


def test_inherited_query_builder_surface(orm_db: DatabaseABC) -> None:
    """select_models() keeps the whole SelectQuery surface."""
    _seed(orm_db)
    orm_db.insert_model(OrmUser(name="Bob", country_code="be")).execute()

    assert orm_db.select_models(OrmUser).count() == 2
    assert orm_db.select_models(OrmUser).where_equals("name", "Nobody").fetch_model() is None

    bob = orm_db.select_models(OrmUser).where_equals("name", "Bob").fetch_model()
    assert bob is not None
    assert bob.name == "Bob"

    names = [user.name for user in orm_db.select_models(OrmUser).order_by_desc("id").limit(1).fetch_models()]
    assert names == ["Bob"]


def test_update_cascades_to_loaded_relations(orm_db: DatabaseABC) -> None:
    user = _seed(orm_db)

    user.name = "Alice Renamed"
    user.posts[0].title = "A1 Renamed"
    orm_db.update_model(user).relation("posts").execute()

    reloaded = orm_db.select_models(OrmUser).relation("posts").fetch_model()

    assert reloaded is not None
    assert reloaded.name == "Alice Renamed"
    assert sorted(post.title for post in reloaded.posts) == ["A1 Renamed", "A2"]


def test_update_columns_restricts_the_written_columns(orm_db: DatabaseABC) -> None:
    user = _seed(orm_db)

    user.name = "Renamed"
    user.country_code = "be"
    orm_db.update_model(user).columns(["name"]).execute()

    row = (
        orm_db.select("orm_users").columns(["name", "country_code"]).where_equals("id", user.id).execute().fetch_dict()
    )

    assert row is not None
    assert row["name"] == "Renamed"
    assert row["country_code"] == "nl"


def test_delete_cascades_bottom_up(orm_db: DatabaseABC) -> None:
    """Children and join rows go before the owner, and shared targets survive."""
    user = _seed(orm_db)

    orm_db.delete_model(user).relation("profile").relation("posts.comments").relation("posts.tags").execute()

    assert orm_db.select("orm_users").count() == 0
    assert orm_db.select("orm_profiles").count() == 0
    assert orm_db.select("orm_posts").count() == 0
    assert orm_db.select("orm_comments").count() == 0
    assert orm_db.select("orm_post_tags").count() == 0
    assert orm_db.select("orm_tags").count() == 2


def test_delete_leaves_unrelated_rows_alone(orm_db: DatabaseABC) -> None:
    _seed(orm_db)
    bob = OrmUser(name="Bob", country_code="be", posts=[OrmPost(user_id=0, title="B1")])
    orm_db.insert_model(bob).relation("posts").execute()

    orm_db.delete_model(bob).relation("posts").execute()

    assert orm_db.select("orm_users").count() == 1
    assert orm_db.select("orm_posts").count() == 2
