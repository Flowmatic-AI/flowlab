from __future__ import annotations

from typing import Annotated

import pytest

from flowlab.modules.db import ModelError
from flowlab.modules.db.database import DB
from flowlab.modules.db.orm import (
    AutoIncrement,
    BelongsTo,
    HasMany,
    HasOne,
    ManyToMany,
    Model,
    PrimaryKey,
    RelationTree,
    belongs_to,
    column,
    has_many,
    has_one,
    many_to_many,
    model_mapper,
    model_meta,
)


class Widget(Model):
    __table__ = "widgets"
    id: AutoIncrement = None
    label: Annotated[str, column(column_name="widget_label")]


class NoTableModel(Model):
    id: AutoIncrement = None


class NoPrimaryKeyModel(Model):
    __table__ = "no_primary_key"
    name: str


class CompositeKeyModel(Model):
    __table__ = "composite_key"
    tenant_id: PrimaryKey[int]
    item_id: PrimaryKey[int]
    name: str


class Author(Model):
    __table__ = "authors"
    id: AutoIncrement = None
    name: str
    profile: HasOne[AuthorProfile] = has_one()
    books: HasMany[Book] = has_many()
    tags: ManyToMany[Tag] = many_to_many("author_tags")


class AuthorProfile(Model):
    __table__ = "author_profiles"
    id: AutoIncrement = None
    author_id: int
    bio: str


class Book(Model):
    __table__ = "books"
    id: AutoIncrement = None
    author_id: int
    title: str
    author: BelongsTo[Author] = belongs_to()


class Tag(Model):
    __table__ = "tags"
    id: AutoIncrement = None
    slug: str


class Cabinet(Model):
    __table__ = "cabinets"
    id: AutoIncrement = None
    code: str
    lock: HasOne[Lock] = has_one(foreign_key="cabinet_code", primary_key="code")
    drawers: HasMany[Drawer] = has_many(foreign_key="owner_code", primary_key="code")
    labels: ManyToMany[Label] = many_to_many(
        "cabinet_labels",
        through_primary_key="cab_code",
        through_foreign_key="label_slug",
        primary_key="code",
        foreign_key="slug",
    )


class Lock(Model):
    __table__ = "locks"
    id: AutoIncrement = None
    cabinet_code: str


class Drawer(Model):
    __table__ = "drawers"
    id: AutoIncrement = None
    owner_code: str


class Label(Model):
    __table__ = "labels"
    slug: PrimaryKey[str]
    text: str


class Badge(Model):
    __table__ = "badges"
    id: AutoIncrement = None
    holder_code: str
    holder: BelongsTo[Cabinet] = belongs_to(foreign_key="holder_code", primary_key="code")


class Category(Model):
    __table__ = "categories"
    id: AutoIncrement = None
    parent_id: int | None = None
    name: str
    parent: BelongsTo[Category] = belongs_to(foreign_key="parent_id")
    children: HasMany[Category] = has_many(foreign_key="parent_id")


def test_table_resolution() -> None:
    assert model_meta(Widget).table == "widgets"


def test_column_mapping_defaults_to_field_name() -> None:
    name_column = model_meta(Author).column_by_field("name")
    assert name_column.column_name == "name"


def test_column_renaming_via_column_helper() -> None:
    meta = model_meta(Widget)
    label_column = meta.column_by_field("label")

    assert label_column.column_name == "widget_label"
    assert meta.column_by_name("widget_label") is label_column


def test_auto_increment_detection() -> None:
    id_column = model_meta(Widget).column_by_field("id")

    assert id_column.primary_key is True
    assert id_column.auto_increment is True


def test_primary_key_annotation_detection() -> None:
    slug_column = model_meta(Label).column_by_field("slug")

    assert slug_column.primary_key is True
    assert slug_column.auto_increment is False


def test_missing_table_raises_model_error() -> None:
    with pytest.raises(ModelError):
        model_meta(NoTableModel)


def test_missing_primary_key_raises_model_error() -> None:
    with pytest.raises(ModelError):
        _ = model_meta(NoPrimaryKeyModel).primary_keys


def test_missing_primary_key_raises_on_primary_key_property_too() -> None:
    with pytest.raises(ModelError):
        _ = model_meta(NoPrimaryKeyModel).primary_key


def test_composite_primary_key_allowed_on_primary_keys() -> None:
    primary_keys = model_meta(CompositeKeyModel).primary_keys

    assert {column.column_name for column in primary_keys} == {"tenant_id", "item_id"}


def test_composite_primary_key_rejected_by_primary_key_property() -> None:
    with pytest.raises(ModelError):
        _ = model_meta(CompositeKeyModel).primary_key


def test_has_one_default_key_names() -> None:
    relation = model_meta(Author).relation("profile")

    assert relation.owner_column == "id"
    assert relation.target_column == "author_id"


def test_has_many_default_key_names() -> None:
    relation = model_meta(Author).relation("books")

    assert relation.owner_column == "id"
    assert relation.target_column == "author_id"


def test_belongs_to_default_key_names() -> None:
    relation = model_meta(Book).relation("author")

    assert relation.owner_column == "author_id"
    assert relation.target_column == "id"


def test_many_to_many_default_key_names() -> None:
    relation = model_meta(Author).relation("tags")

    assert relation.through == "author_tags"
    assert relation.owner_column == "id"
    assert relation.target_column == "id"
    assert relation.through_owner_column == "author_id"
    assert relation.through_target_column == "tag_id"


def test_has_one_explicit_key_override() -> None:
    relation = model_meta(Cabinet).relation("lock")

    assert relation.owner_column == "code"
    assert relation.target_column == "cabinet_code"


def test_has_many_explicit_key_override() -> None:
    relation = model_meta(Cabinet).relation("drawers")

    assert relation.owner_column == "code"
    assert relation.target_column == "owner_code"


def test_belongs_to_explicit_key_override() -> None:
    relation = model_meta(Badge).relation("holder")

    assert relation.owner_column == "holder_code"
    assert relation.target_column == "code"


def test_many_to_many_explicit_key_override() -> None:
    relation = model_meta(Cabinet).relation("labels")

    assert relation.through == "cabinet_labels"
    assert relation.owner_column == "code"
    assert relation.target_column == "slug"
    assert relation.through_owner_column == "cab_code"
    assert relation.through_target_column == "label_slug"


def test_forward_referenced_relation_target_resolves() -> None:
    relation = model_meta(Author).relation("books")

    assert relation.target is Book


def test_self_referencing_relation_targets_resolve() -> None:
    parent_relation = model_meta(Category).relation("parent")
    children_relation = model_meta(Category).relation("children")

    assert parent_relation.target is Category
    assert children_relation.target is Category
    assert parent_relation.owner_column == "parent_id"
    assert parent_relation.target_column == "id"
    assert children_relation.owner_column == "id"
    assert children_relation.target_column == "parent_id"


def test_column_identifiers() -> None:
    identifiers = model_meta(Widget).column_identifiers()

    assert identifiers == {"id": ["widgets", "id"], "widget_label": ["widgets", "widget_label"]}


def test_to_model_maps_known_columns_and_ignores_unmapped_keys() -> None:
    widget = model_mapper(Widget).to_model({"id": 1, "widget_label": "Left", "extra_column": "ignored"})

    assert widget.id == 1
    assert widget.label == "Left"


def test_to_models_maps_every_row() -> None:
    widgets = model_mapper(Widget).to_models([{"id": 1, "widget_label": "Left"}, {"id": 2, "widget_label": "Right"}])

    assert [(widget.id, widget.label) for widget in widgets] == [(1, "Left"), (2, "Right")]


def test_to_row_keys_the_values_by_column_name() -> None:
    assert model_mapper(Widget).to_row(Widget(id=1, label="Left")) == {"id": 1, "widget_label": "Left"}


def test_the_mapper_of_a_model_class_is_shared() -> None:
    mapper = model_mapper(Widget)

    assert model_mapper(Widget) is mapper
    assert mapper.model is Widget
    assert mapper.meta is model_meta(Widget)


def test_column_value_reads_and_set_column_value_writes_a_field() -> None:
    mapper = model_mapper(Widget)
    widget = Widget(label="Left")
    label = mapper.meta.column_by_name("widget_label")

    assert mapper.column_value(widget, label) == "Left"

    mapper.set_column_value(widget, label, "Right")

    assert widget.label == "Right"
    assert "label" in widget.model_fields_set


def test_key_value_and_primary_key_value_read_a_field_by_column_name() -> None:
    mapper = model_mapper(Widget)
    widget = Widget(id=7, label="Left")

    assert mapper.key_value(widget, "widget_label") == "Left"
    assert mapper.primary_key_value(widget) == 7

    with pytest.raises(ModelError):
        mapper.key_value(widget, "no_such_column")


def test_related_models_normalizes_a_relation_field_to_a_list() -> None:
    mapper = model_mapper(Author)
    author = Author(name="Ann")
    profile = model_meta(Author).relation("profile")
    books = model_meta(Author).relation("books")

    assert mapper.related_models(author, profile) == []
    assert mapper.related_models(author, books) == []

    bio = AuthorProfile(author_id=1, bio="Writes")
    book = Book(author_id=1, title="First")

    mapper.set_relation(author, profile, bio)
    mapper.set_relation(author, books, [book])

    assert mapper.related_models(author, profile) == [bio]
    assert mapper.related_models(author, books) == [book]


def test_is_relation_loaded_reports_which_relations_were_set() -> None:
    mapper = model_mapper(Author)
    author = mapper.to_model({"id": 1, "name": "Ann"})

    assert mapper.is_relation_loaded(author, "books") is False

    mapper.set_relation(author, model_meta(Author).relation("books"), [])

    assert mapper.is_relation_loaded(author, "books") is True

    with pytest.raises(ModelError):
        mapper.is_relation_loaded(author, "no_such_relation")


def test_relation_tree_add_simple_path() -> None:
    tree = RelationTree(Author)
    tree.add("books")

    assert set(tree.nodes) == {"books"}
    assert tree.nodes["books"].relation.field_name == "books"
    assert tree.nodes["books"].children == {}


def test_relation_tree_add_nested_path_creates_intermediate_node() -> None:
    tree = RelationTree(Book)
    tree.add("author.profile")

    assert set(tree.nodes) == {"author"}
    author_node = tree.nodes["author"]
    assert set(author_node.children) == {"profile"}
    assert author_node.children["profile"].relation.field_name == "profile"


def test_relation_tree_shares_intermediate_node_for_sibling_paths() -> None:
    tree = RelationTree(Book)
    tree.add("author.profile")
    tree.add("author.books")

    assert len(tree.nodes) == 1
    author_node = tree.nodes["author"]
    assert set(author_node.children) == {"profile", "books"}


def test_relation_tree_is_empty() -> None:
    tree = RelationTree(Author)
    assert tree.is_empty is True

    tree.add("books")
    assert tree.is_empty is False


def test_relation_tree_stores_customize_callback() -> None:
    def order_by_id(query: object) -> None:
        pass

    tree = RelationTree(Author)
    tree.add("books", order_by_id)

    assert tree.nodes["books"].customize is order_by_id


def test_relation_tree_add_unknown_relation_raises_model_error() -> None:
    tree = RelationTree(Author)

    with pytest.raises(ModelError):
        tree.add("nonexistent")


def test_relation_tree_add_unknown_nested_relation_raises_model_error() -> None:
    tree = RelationTree(Book)

    with pytest.raises(ModelError):
        tree.add("author.nonexistent")


def test_relation_tree_add_malformed_path_raises_model_error() -> None:
    tree = RelationTree(Author)

    with pytest.raises(ModelError):
        tree.add("")

    with pytest.raises(ModelError):
        tree.add("books..name")


def test_describe_table_reads_the_table_description_off_the_database() -> None:
    db = DB.connect_sqlite(":memory:")
    db.create_table("widgets").identity("id").string("widget_label").execute()

    description = model_mapper(Widget).describe_table(db)

    assert [column.name for column in description.columns] == ["id", "widget_label"]
    assert description == db.describe_table("widgets")
