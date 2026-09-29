from flowlab._exceptions import SchemaMismatch
from flowlab.modules.auth._models import ApiKey, user_model
from flowlab.modules.db import DB as Database
from flowlab.modules.db.orm import Model, model_meta


def check_schema(db: Database) -> None:
    tables = set(db.list_tables())
    missing: list[str] = []
    models: list[type[Model]] = [user_model(), ApiKey]

    for model in models:
        table = model.__table__

        if table not in tables:
            missing.append(f"table {table}")
            continue

        columns = {column.name for column in db.describe_table(table).columns}
        missing.extend(
            f"column {table}.{column.column_name}"
            for column in model_meta(model).columns
            if column.column_name not in columns
        )

    if missing and all(item.startswith(f"column {user_model().__table__}.") for item in missing):
        raise SchemaMismatch(
            "auth",
            missing,
            f"Add them to the {user_model().__table__} table in a migration of your own "
            "(`migrations:make`), then `migrations:up`",
        )

    if missing:
        raise SchemaMismatch("auth", missing)
