from fastapi import HTTPException, status

from flowlab.modules.auth._models import ApiKey, BaseUser, user_model
from flowlab.modules.auth._security import API_KEY_HINT_LENGTH, generate_api_key, hash_api_key
from flowlab.modules.db import identifier, now
from flowlab.modules.db.database import DB as Database
from flowlab.modules.db.orm import SelectModelQuery


def create(db: Database, user: BaseUser, name: str) -> tuple[ApiKey, str]:
    if user.id is None:
        raise ValueError("cannot create an API key for a user that has no id")

    token = generate_api_key()
    api_key = ApiKey(
        user_id=user.id,
        name=name,
        hint=token[:API_KEY_HINT_LENGTH],
        token_hash=hash_api_key(token),
    )

    db.insert_model(api_key).omit_null_values().returning().execute()

    return api_key, token


def owned_by(db: Database, user: BaseUser) -> SelectModelQuery[ApiKey]:
    return db.select_models(ApiKey).where_equals("user_id", user.id).where_is_null("deleted_at").order_by_desc("id")


def find_owned(db: Database, user: BaseUser, api_key_id: int) -> ApiKey:
    api_key = owned_by(db, user).where_equals("id", api_key_id).fetch_model()

    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    return api_key


def revoke(db: Database, api_key: ApiKey) -> None:
    db.update(ApiKey.__table__).updates({"deleted_at": now(), "updated_at": now()}).where_equals(
        "id", api_key.id
    ).execute()


def user_from_api_key(db: Database, token: str) -> BaseUser | None:
    users = user_model()
    live_key = (
        db.select(ApiKey.__table__)
        .where_equals([ApiKey.__table__, "user_id"], identifier([users.__table__, "id"]))
        .where_equals([ApiKey.__table__, "token_hash"], hash_api_key(token))
        .where_is_null([ApiKey.__table__, "deleted_at"])
    )

    return db.select_models(users).where_exists(live_key).where_is_null([users.__table__, "deleted_at"]).fetch_model()
