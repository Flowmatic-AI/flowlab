from __future__ import annotations

from flowlab.modules.db.database import DB
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
from flowlab.modules.db.query import SelectQuery


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


class Tag(Model):
    __table__ = "tags"
    id: AutoIncrement = None
    slug: str


def _build_database() -> DB:
    db = DB.connect_sqlite(":memory:")
    db.create_table("authors").identity("id").string("name").execute()
    db.create_table("author_profiles").identity("id").integer("author_id").string("bio").execute()
    db.create_table("posts").identity("id").integer("author_id").string("title").execute()
    db.create_table("comments").identity("id").integer("post_id").string("body").execute()
    db.create_table("comment_flags").identity("id").integer("comment_id").string("reason").execute()
    db.create_table("tags").identity("id").string("slug").execute()
    db.create_table("author_tags").integer("author_id").integer("tag_id").execute()
    return db


def test_has_one_relation_loads_related_row() -> None:
    db = _build_database()
    db.insert("authors").values({"id": 1, "name": "Alice"}).execute()
    db.insert("author_profiles").values({"id": 1, "author_id": 1, "bio": "a bio"}).execute()

    author = db.select_models(Author).relation("profile").where_equals("id", 1).fetch_model()

    assert author is not None
    assert author.profile is not None
    assert author.profile.bio == "a bio"


def test_belongs_to_relation_loads_related_row() -> None:
    db = _build_database()
    db.insert("authors").values({"id": 1, "name": "Alice"}).execute()
    db.insert("posts").values({"id": 10, "author_id": 1, "title": "First"}).execute()

    post = db.select_models(Post).relation("author").where_equals("id", 10).fetch_model()

    assert post is not None
    assert post.author is not None
    assert post.author.name == "Alice"


def test_has_many_relation_loads_related_rows() -> None:
    db = _build_database()
    db.insert("authors").values({"id": 1, "name": "Alice"}).execute()
    db.insert("posts").values(
        {"id": 10, "author_id": 1, "title": "First"},
        {"id": 11, "author_id": 1, "title": "Second"},
    ).execute()

    author = db.select_models(Author).relation("posts").where_equals("id", 1).fetch_model()

    assert author is not None
    titles = sorted(post.title for post in author.posts)
    assert titles == ["First", "Second"]


def test_many_to_many_relation_loads_related_rows() -> None:
    db = _build_database()
    db.insert("authors").values({"id": 1, "name": "Alice"}).execute()
    db.insert("tags").values({"id": 1, "slug": "fiction"}, {"id": 2, "slug": "essay"}).execute()
    db.insert("author_tags").values({"author_id": 1, "tag_id": 1}, {"author_id": 1, "tag_id": 2}).execute()

    author = db.select_models(Author).relation("tags").where_equals("id", 1).fetch_model()

    assert author is not None
    slugs = sorted(tag.slug for tag in author.tags)
    assert slugs == ["essay", "fiction"]


def test_nested_relation_path_several_levels_deep() -> None:
    db = _build_database()
    db.insert("authors").values({"id": 1, "name": "Alice"}).execute()
    db.insert("posts").values({"id": 10, "author_id": 1, "title": "First"}).execute()
    db.insert("comments").values({"id": 100, "post_id": 10, "body": "nice"}).execute()
    db.insert("comment_flags").values({"id": 1000, "comment_id": 100, "reason": "spam"}).execute()

    author = db.select_models(Author).relation("posts.comments.flags").where_equals("id", 1).fetch_model()

    assert author is not None
    assert len(author.posts) == 1
    post = author.posts[0]
    assert len(post.comments) == 1
    comment = post.comments[0]
    assert len(comment.flags) == 1
    assert comment.flags[0].reason == "spam"


def test_relation_with_no_matching_children_is_empty_list_not_error() -> None:
    db = _build_database()
    db.insert("authors").values({"id": 1, "name": "Alice"}).execute()

    author = db.select_models(Author).relation("posts").where_equals("id", 1).fetch_model()

    assert author is not None
    assert author.posts == []


def test_relation_with_no_matching_row_is_none_not_error() -> None:
    db = _build_database()
    db.insert("authors").values({"id": 1, "name": "Alice"}).execute()

    author = db.select_models(Author).relation("profile").where_equals("id", 1).fetch_model()

    assert author is not None
    assert author.profile is None


def test_null_foreign_key_resolves_relation_to_none() -> None:
    db = _build_database()
    db.insert("posts").values({"id": 10, "author_id": None, "title": "Orphan"}).execute()

    post = db.select_models(Post).relation("author").where_equals("id", 10).fetch_model()

    assert post is not None
    assert post.author_id is None
    assert post.author is None


def test_customize_callback_orders_has_many_results() -> None:
    db = _build_database()
    db.insert("authors").values({"id": 1, "name": "Alice"}).execute()
    db.insert("posts").values(
        {"id": 10, "author_id": 1, "title": "First"},
        {"id": 11, "author_id": 1, "title": "Second"},
        {"id": 12, "author_id": 1, "title": "Third"},
    ).execute()

    def order_descending(query: SelectQuery) -> None:
        query.order_by_desc("id")

    author = db.select_models(Author).relation("posts", order_descending).where_equals("id", 1).fetch_model()

    assert author is not None
    assert [post.id for post in author.posts] == [12, 11, 10]


def test_belongs_to_shares_a_single_instance_across_parents() -> None:
    db = _build_database()
    db.insert("authors").values({"id": 1, "name": "Alice"}).execute()
    db.insert("posts").values(
        {"id": 10, "author_id": 1, "title": "First"},
        {"id": 11, "author_id": 1, "title": "Second"},
    ).execute()

    posts = db.select_models(Post).relation("author").order_by_asc("id").fetch_models()

    assert len(posts) == 2
    assert posts[0].author is not None
    assert posts[0].author is posts[1].author
