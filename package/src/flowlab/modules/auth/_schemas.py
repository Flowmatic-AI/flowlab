from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, create_model, field_validator

from flowlab.modules.auth._models import ApiKey, BaseUser, fillable_fields
from flowlab.modules.auth._security import MAX_PASSWORD_BYTES


class Credentials(BaseModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def _password_within_byte_limit(cls, value: str) -> str:
        if len(value.encode()) > MAX_PASSWORD_BYTES:
            raise ValueError(f"password may not exceed {MAX_PASSWORD_BYTES} bytes")

        return value


class Registration(Credentials):
    def attributes(self) -> dict[str, Any]:
        return self.model_dump(exclude={"email", "password"})


class Token[UserT: BaseUser](BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserT


class ApiKeyCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)


class NewApiKey(BaseModel):
    api_key: ApiKey
    token: str


def registration_schema(user_model: type[BaseUser]) -> type[Registration]:
    fields: dict[str, Any] = {
        name: (user_model.model_fields[name].annotation, user_model.model_fields[name])
        for name in fillable_fields(user_model)
    }

    return create_model(f"{user_model.__name__}Registration", __base__=Registration, **fields)
