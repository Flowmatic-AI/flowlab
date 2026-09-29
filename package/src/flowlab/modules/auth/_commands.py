import inspect
import types
from collections.abc import Callable
from typing import Annotated, Any, Union, get_args, get_origin

import typer
from fastapi import HTTPException
from pydantic import ValidationError

from flowlab._database import get_db
from flowlab._routing import CommandRouter
from flowlab.modules.auth import _api_keys
from flowlab.modules.auth import _users as service
from flowlab.modules.auth._models import BaseUser, fillable_fields
from flowlab.modules.auth._schemas import ApiKeyCreate, registration_schema

OPTION_TYPES = (str, int, float, bool)


def _option_type(annotation: Any) -> Any:
    if annotation in OPTION_TYPES:
        return annotation

    if get_origin(annotation) in (Union, types.UnionType):
        members = [member for member in get_args(annotation) if member is not type(None)]

        if len(members) == 1 and members[0] in OPTION_TYPES:
            return members[0] | None

    return str


def create_user_command(user_model: type[BaseUser]) -> Callable[..., None]:
    registration = registration_schema(user_model)
    fillable = fillable_fields(user_model)

    def create_user(**options: Any) -> None:
        values = {name: value for name, value in options.items() if value is not None}

        try:
            body = registration(**values)
        except ValidationError as error:
            for detail in error.errors():
                typer.echo(f"{detail['loc'][0]}: {detail['msg']}", err=True)

            raise typer.Exit(1) from None

        try:
            user = service.register(get_db(), body.email, body.password, body.attributes())
        except HTTPException as error:
            typer.echo(error.detail, err=True)
            raise typer.Exit(1) from None

        typer.echo(f"Created user {user.id} <{user.email}>")

    parameters = [
        inspect.Parameter(
            "email",
            inspect.Parameter.KEYWORD_ONLY,
            annotation=Annotated[str, typer.Option(help="Login email.")],
        )
    ]

    for name in fillable:
        field = user_model.model_fields[name]
        required = field.is_required()
        option_type = _option_type(field.annotation)

        parameters.append(
            inspect.Parameter(
                name,
                inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[
                    option_type if required else option_type | None,
                    typer.Option(help=field.description or f"The user's {name.replace('_', ' ')}."),
                ],
                default=inspect.Parameter.empty if required else None,
            )
        )

    parameters.append(
        inspect.Parameter(
            "password",
            inspect.Parameter.KEYWORD_ONLY,
            annotation=Annotated[str, typer.Option(prompt=True, hide_input=True, confirmation_prompt=True)],
        )
    )

    create_user.__signature__ = inspect.Signature(parameters)  # type: ignore[attr-defined]
    create_user.__annotations__ = {parameter.name: parameter.annotation for parameter in parameters}

    return create_user


def create_api_key(
    email: Annotated[str, typer.Option(help="Email of the user who owns the key.")],
    name: Annotated[str, typer.Option(help="What the key is for, e.g. claude-code.")],
) -> None:
    try:
        body = ApiKeyCreate(name=name)
    except ValidationError as error:
        typer.echo(f"name: {error.errors()[0]['msg']}", err=True)
        raise typer.Exit(1) from None

    db = get_db()
    user = service.find_by_email(db, email)

    if user is None:
        typer.echo(f"No user with email {email}", err=True)
        raise typer.Exit(1)

    api_key, token = _api_keys.create(db, user, body.name)

    typer.echo(f"Created API key {api_key.id} ({api_key.name}) for <{user.email}>. It is shown once:")
    typer.echo(token)


def auth_commands(user_model: type[BaseUser]) -> CommandRouter:
    commands = CommandRouter()
    commands.command("users:create", help="Create a user.")(create_user_command(user_model))
    commands.command("api-keys:create", help="Create an API key for a user and print its token once.")(create_api_key)

    return commands
