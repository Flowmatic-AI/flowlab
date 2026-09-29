from __future__ import annotations

import pytest

from flowlab.modules.db import DB, ModelError
from flowlab.modules.db.orm import (
    AutoIncrement,
    BelongsTo,
    HasMany,
    HasOne,
    ManyToMany,
    Model,
    belongs_to,
    has_many,
    has_one,
    many_to_many,
)


class Author(Model):
    __table__ = "authors"
    id: AutoIncrement = None
    name: str
    profile: HasOne[AuthorProfile] = has_one()
    posts: HasMany[Post] = has_many()
    tags: ManyToMany[Tag] = many_to_many("author_tags")


class AuthorProfile(Model):
    __table__ = "author_profiles"
    id: AutoIncrement = None
    author_id: int
    bio: str
    nickname: str | None = None


class Post(Model):
    __table__ = "posts"
    id: AutoIncrement = None
    author_id: int | None = None
    title: str
    author: BelongsTo[Author] = belongs_to()
    comments: HasMany[Comment] = has_many()


class Comment(Model):
    __table__ = "comments"
    id: AutoIncrement = None
    post_id: int
    body: str
    flags: HasMany[CommentFlag] = has_many()


class CommentFlag(Model):
    __table__ = "comment_flags"
    id: AutoIncrement = None
    comment_id: int
    reason: str


class Defaulted(Model):
    __table__ = "defaulted"
    id: AutoIncrement = None
    name: str
    nickname: str | None = None


class Tag(Model):
    __table__ = "tags"
    id: AutoIncrement = None
    slug: str
    authors: ManyToMany[Author] = many_to_many("author_tags")


def _build_database() -> DB:
    db = DB.connect_sqlite(":memory:")
    _create_tables(db)
    return db


def _build_recording_database() -> tuple[DB, list[str]]:
    """A database that records every statement it runs, so a RETURNING clause can be asserted."""
    statements: list[str] = []
    db = DB.connect_sqlite(":memory:", debug_callback=lambda sql, duration, error: statements.append(sql))
    _create_tables(db)
    statements.clear()

    return db, statements


def _create_tables(db: DB) -> None:
    db.create_table("authors").identity("id").string("name").execute()
    (
        db.create_table("author_profiles")
        .identity("id")
        .integer("author_id")
        .string("bio")
        .string("nickname", default="anon")
        .execute()
    )
    db.create_table("posts").identity("id").integer("author_id").string("title").execute()
    db.create_table("comments").identity("id").integer("post_id").string("body").execute()
    db.create_table("comment_flags").identity("id").integer("comment_id").string("reason").execute()
    db.create_table("tags").identity("id").string("slug").execute()
    db.create_table("author_tags").integer("author_id").integer("tag_id").execute()
    db.create_table("defaulted").identity("id").string("name").string("nickname", default="anon").execute()


def test_insert_model_fills_auto_increment_primary_key() -> None:
    db = _build_database()
    author = Author(name="Alice")

    inserted = db.insert_model(author).execute()

    assert inserted == [author]
    assert author.id is not None

    row = db.select("authors").where_equals("id", author.id).execute().fetch_dict()
    assert row is not None
    assert row["name"] == "Alice"


def test_insert_models_fills_auto_increment_for_each_model() -> None:
    db = _build_database()
    authors = [Author(name="Alice"), Author(name="Bob")]

    db.insert_models(authors).execute()

    ids = {author.id for author in authors}
    assert None not in ids
    assert len(ids) == 2


def test_auto_increment_column_is_never_inserted_and_its_value_is_replaced() -> None:
    db, statements = _build_recording_database()
    author = Author(id=99, name="Zoe")

    db.insert_model(author).execute()

    assert statements == ['INSERT INTO "authors" ("name") VALUES (\'Zoe\') RETURNING "id"']
    assert author.id == 1
    row = db.select("authors").where_equals("id", 1).execute().fetch_dict()
    assert row is not None
    assert row["name"] == "Zoe"


def test_insert_model_cascades_belongs_to_and_sets_foreign_key() -> None:
    db = _build_database()
    author = Author(name="Bob")
    post = Post(title="Guide", author=author)

    db.insert_model(post).relation("author").execute()

    assert post.author is not None
    assert post.author.id is not None
    assert post.author_id == post.author.id

    row = db.select("posts").where_equals("id", post.id).execute().fetch_dict()
    assert row is not None
    assert row["author_id"] == post.author.id


def test_insert_model_cascades_has_many_and_sets_foreign_key_on_children() -> None:
    db = _build_database()
    comment = Comment(post_id=0, body="Nice")
    post = Post(title="Guide", comments=[comment])

    db.insert_model(post).relation("comments").execute()

    assert comment.id is not None
    assert comment.post_id == post.id

    row = db.select("comments").where_equals("id", comment.id).execute().fetch_dict()
    assert row is not None
    assert row["post_id"] == post.id


def test_insert_model_cascades_many_to_many_and_inserts_join_rows() -> None:
    db = _build_database()
    tag = Tag(slug="fiction")
    author = Author(name="Alice", tags=[tag])

    db.insert_model(author).relation("tags").execute()

    assert tag.id is not None
    join_row = db.select("author_tags").where_equals("author_id", author.id).execute().fetch_dict()
    assert join_row is not None
    assert join_row["tag_id"] == tag.id


def test_insert_model_cascades_nested_relation_path() -> None:
    db = _build_database()
    comment = Comment(post_id=0, body="Nice")
    post = Post(title="Guide", comments=[comment])
    author = Author(name="Carol", posts=[post])

    db.insert_model(author).relation("posts.comments").execute()

    assert post.id is not None
    assert post.author_id == author.id
    assert comment.id is not None
    assert comment.post_id == post.id


def test_insert_models_empty_list_is_noop_and_relation_does_not_raise() -> None:
    db = _build_database()
    authors: list[Author] = []

    result = db.insert_models(authors).relation("posts").execute()

    assert result == []


def test_insert_model_returns_the_auto_increment_key_by_default() -> None:
    db, statements = _build_recording_database()

    db.insert_model(Author(name="Alice")).execute()

    assert statements == ['INSERT INTO "authors" ("name") VALUES (\'Alice\') RETURNING "id"']


def test_insert_model_returning_adds_the_auto_increment_key_to_the_named_columns() -> None:
    db, statements = _build_recording_database()
    author = Author(name="Alice")

    db.insert_model(author).returning(["name"]).execute()

    assert statements == ['INSERT INTO "authors" ("name") VALUES (\'Alice\') RETURNING "id", "name"']
    assert author.id is not None


def test_insert_model_returning_does_not_repeat_the_auto_increment_key() -> None:
    db, statements = _build_recording_database()

    db.insert_model(Author(name="Alice")).returning(["name", "id"]).execute()

    assert statements == ['INSERT INTO "authors" ("name") VALUES (\'Alice\') RETURNING "id", "name"']


def test_insert_model_returning_without_columns_reads_every_column() -> None:
    db, statements = _build_recording_database()
    author = Author(name="Alice")

    db.insert_model(author).returning().execute()

    assert statements == ['INSERT INTO "authors" ("name") VALUES (\'Alice\') RETURNING *']
    assert author.id is not None


def test_insert_model_returning_applies_to_the_root_models_only() -> None:
    db, statements = _build_recording_database()
    post = Post(title="Guide", author=Author(name="Bob"))

    db.insert_model(post).relation("author").returning(["title"]).execute()

    assert statements == [
        'INSERT INTO "authors" ("name") VALUES (\'Bob\') RETURNING "id"',
        'INSERT INTO "posts" ("author_id", "title") VALUES (1, \'Guide\') RETURNING "id", "title"',
    ]


def test_insert_models_returning_reads_every_row_back_onto_its_own_model() -> None:
    db, statements = _build_recording_database()
    authors = [Author(name="Alice"), Author(name="Bob")]

    db.insert_models(authors).returning(["name"]).execute()

    assert statements == [
        'INSERT INTO "authors" ("name") VALUES (\'Alice\') RETURNING "id", "name"',
        'INSERT INTO "authors" ("name") VALUES (\'Bob\') RETURNING "id", "name"',
    ]
    assert [author.name for author in authors] == ["Alice", "Bob"]
    assert None not in [author.id for author in authors]


def test_none_columns_are_inserted_as_null_by_default() -> None:
    db, statements = _build_recording_database()
    model = Defaulted(name="Zoe")

    db.insert_model(model).returning().execute()

    assert statements == ['INSERT INTO "defaulted" ("name", "nickname") VALUES (\'Zoe\', NULL) RETURNING *']
    assert model.nickname is None


def test_omit_null_values_leaves_none_columns_out_of_the_insert() -> None:
    db, statements = _build_recording_database()
    model = Defaulted(name="Zoe")

    db.insert_model(model).omit_null_values().returning().execute()

    assert statements == ['INSERT INTO "defaulted" ("name") VALUES (\'Zoe\') RETURNING *']
    assert model.nickname == "anon"


def test_omit_null_values_applies_to_cascaded_relations_too() -> None:
    db = _build_database()
    author = Author(name="Alice", profile=AuthorProfile(author_id=0, bio="Writes"))

    db.insert_model(author).relation("profile").omit_null_values().execute()

    row = db.select("author_profiles").execute().fetch_dict()
    assert row is not None
    assert row["nickname"] == "anon"


def test_insert_model_returning_unknown_column_name_raises_model_error() -> None:
    db = _build_database()

    with pytest.raises(ModelError):
        db.insert_model(Author(name="Alice")).returning(["nope"]).execute()


def test_insert_models_requires_same_class() -> None:
    db = _build_database()

    with pytest.raises(ModelError):
        db.insert_models([Author(name="Alice"), Tag(slug="x")]).execute()


def test_update_model_writes_non_primary_key_columns() -> None:
    db = _build_database()
    author = Author(name="Alice")
    db.insert_model(author).execute()

    author.name = "Alicia"
    db.update_model(author).execute()

    row = db.select("authors").where_equals("id", author.id).execute().fetch_dict()
    assert row is not None
    assert row["name"] == "Alicia"


def test_update_models_updates_every_model() -> None:
    db = _build_database()
    authors = [Author(name="Alice"), Author(name="Bob")]
    db.insert_models(authors).execute()

    for author in authors:
        author.name = author.name.upper()

    db.update_models(authors).execute()

    rows = db.select("authors").order_by_asc("id").execute().fetch_dicts()
    assert [row["name"] for row in rows] == ["ALICE", "BOB"]


def test_update_model_raises_model_error_when_primary_key_is_none() -> None:
    db = _build_database()
    author = Author(name="Alice")

    with pytest.raises(ModelError):
        db.update_model(author).execute()


def test_update_columns_empty_list_writes_nothing() -> None:
    db = _build_database()
    author = Author(name="Alice")
    db.insert_model(author).execute()

    author.name = "Ignored"
    db.update_model(author).columns([]).execute()

    row = db.select("authors").where_equals("id", author.id).execute().fetch_dict()
    assert row is not None
    assert row["name"] == "Alice"


def test_update_columns_restricts_to_named_columns_only() -> None:
    db = _build_database()
    author = Author(name="Alice")
    db.insert_model(author).execute()
    assert author.id is not None
    profile = AuthorProfile(id=1, author_id=author.id, bio="old bio")
    db.insert_model(profile).execute()

    profile.bio = "new bio"
    profile.author_id = 999
    db.update_model(profile).columns(["bio"]).execute()

    row = db.select("author_profiles").where_equals("id", profile.id).execute().fetch_dict()
    assert row is not None
    assert row["bio"] == "new bio"
    assert row["author_id"] == author.id


def test_update_columns_unknown_column_name_raises_model_error() -> None:
    db = _build_database()
    author = Author(name="Alice")
    db.insert_model(author).execute()

    with pytest.raises(ModelError):
        db.update_model(author).columns(["nonexistent"]).execute()


def test_update_model_cascades_to_loaded_relations() -> None:
    db = _build_database()
    author = Author(name="Alice")
    db.insert_model(author).execute()
    post = Post(title="Old title", author_id=author.id)
    db.insert_model(post).execute()

    author.posts = [post]
    post.title = "New title"
    db.update_model(author).relation("posts").execute()

    row = db.select("posts").where_equals("id", post.id).execute().fetch_dict()
    assert row is not None
    assert row["title"] == "New title"


def test_update_many_to_many_updates_targets_and_leaves_join_table_untouched() -> None:
    db = _build_database()
    author = Author(name="Alice")
    db.insert_model(author).execute()
    tag = Tag(slug="fiction")
    db.insert_model(tag).execute()
    db.insert("author_tags").values({"author_id": author.id, "tag_id": tag.id}).execute()

    author.tags = [tag]
    tag.slug = "nonfiction"
    db.update_model(author).relation("tags").execute()

    row = db.select("tags").where_equals("id", tag.id).execute().fetch_dict()
    assert row is not None
    assert row["slug"] == "nonfiction"

    join_rows = db.select("author_tags").execute().fetch_dicts()
    assert join_rows == [{"author_id": author.id, "tag_id": tag.id}]


def test_update_models_empty_list_is_noop() -> None:
    db = _build_database()
    authors: list[Author] = []

    result = db.update_models(authors).relation("posts").execute()

    assert result == []


def test_update_models_requires_same_class() -> None:
    db = _build_database()

    with pytest.raises(ModelError):
        db.update_models([Author(name="Alice"), Tag(slug="x")]).execute()


def test_delete_model_cascades_has_many_leaf_relation() -> None:
    db = _build_database()
    author = Author(name="Alice")
    db.insert_model(author).execute()
    post = Post(title="Guide", author_id=author.id)
    db.insert_model(post).execute()
    assert post.id is not None
    comment = Comment(post_id=post.id, body="Nice")
    db.insert_model(comment).execute()

    db.delete_model(post).relation("comments").execute()

    assert db.select("posts").where_equals("id", post.id).execute().fetch_dict() is None
    assert db.select("comments").where_equals("id", comment.id).execute().fetch_dict() is None


def test_delete_model_cascades_nested_relation_path() -> None:
    db = _build_database()
    post = Post(title="Guide", author_id=None)
    db.insert_model(post).execute()
    assert post.id is not None
    comment = Comment(post_id=post.id, body="Nice")
    db.insert_model(comment).execute()
    assert comment.id is not None
    flag = CommentFlag(comment_id=comment.id, reason="spam")
    db.insert_model(flag).execute()

    db.delete_model(post).relation("comments.flags").execute()

    assert db.select("comment_flags").where_equals("id", flag.id).execute().fetch_dict() is None
    assert db.select("comments").where_equals("id", comment.id).execute().fetch_dict() is None
    assert db.select("posts").where_equals("id", post.id).execute().fetch_dict() is None


def test_delete_model_many_to_many_removes_only_join_rows() -> None:
    db = _build_database()
    author = Author(name="Alice")
    db.insert_model(author).execute()
    tag = Tag(slug="fiction")
    db.insert_model(tag).execute()
    db.insert("author_tags").values({"author_id": author.id, "tag_id": tag.id}).execute()

    db.delete_model(author).relation("tags").execute()

    assert db.select("author_tags").execute().fetch_dicts() == []
    assert db.select("tags").where_equals("id", tag.id).execute().fetch_dict() is not None


def test_delete_model_cascades_belongs_to_target_after_owner() -> None:
    db = _build_database()
    author = Author(name="Alice")
    db.insert_model(author).execute()
    post = Post(title="Guide", author_id=author.id)
    db.insert_model(post).execute()

    loaded_post = db.select_models(Post).relation("author").where_equals("id", post.id).fetch_model()
    assert loaded_post is not None

    db.delete_model(loaded_post).relation("author").execute()

    assert db.select("posts").where_equals("id", post.id).execute().fetch_dict() is None
    assert db.select("authors").where_equals("id", author.id).execute().fetch_dict() is None


def test_delete_model_skips_relation_when_no_matching_rows_exist() -> None:
    db = _build_database()
    author = Author(name="Alice")
    db.insert_model(author).execute()

    db.delete_model(author).relation("posts").execute()

    assert db.select("authors").where_equals("id", author.id).execute().fetch_dict() is None


def test_delete_model_skips_belongs_to_relation_when_foreign_key_is_null() -> None:
    db = _build_database()
    post = Post(title="Orphan", author_id=None)
    db.insert_model(post).execute()

    db.delete_model(post).relation("author").execute()

    assert db.select("posts").where_equals("id", post.id).execute().fetch_dict() is None


def test_delete_many_to_many_with_children_raises_model_error() -> None:
    db = _build_database()
    author = Author(name="Alice")
    db.insert_model(author).execute()

    with pytest.raises(ModelError):
        db.delete_model(author).relation("tags.authors").execute()


def test_delete_models_empty_list_is_noop() -> None:
    db = _build_database()
    authors: list[Author] = []

    db.delete_models(authors).relation("posts").execute()


def test_delete_models_requires_same_class() -> None:
    db = _build_database()

    with pytest.raises(ModelError):
        db.delete_models([Author(name="Alice"), Tag(slug="x")]).execute()
