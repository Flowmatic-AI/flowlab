import sys
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _env_files() -> tuple[Path, ...]:
    files = [Path(".env").resolve()]
    for name in ("__main__", "__mp_main__"):
        script = getattr(sys.modules.get(name), "__file__", None)

        if script is not None:
            files.append(Path(script).resolve().parent / ".env")

    return tuple(dict.fromkeys(files))


SETTINGS_CONFIG = SettingsConfigDict(env_file=_env_files(), env_file_encoding="utf-8", extra="ignore")

CommaSeparated = Annotated[list[str], NoDecode]


class AppEnv(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class DBDriver(StrEnum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MARIADB = "mariadb"


class CacheDriver(StrEnum):
    MEMORY = "memory"
    DATABASE = "database"
    REDIS = "redis"
    VALKEY = "valkey"
    MEMCACHED = "memcached"


class QueueDriver(StrEnum):
    SYNC = "sync"
    DATABASE = "database"
    REDIS = "redis"
    VALKEY = "valkey"


DB_DRIVER_ALIASES = {"postgres": DBDriver.POSTGRESQL}

DB_DEFAULT_NAMES = {DBDriver.SQLITE: "database.sqlite"}

DB_DEFAULT_PORTS = {
    DBDriver.POSTGRESQL: 5432,
    DBDriver.MYSQL: 3306,
    DBDriver.MARIADB: 3306,
}

DB_DEFAULT_USERS = {
    DBDriver.POSTGRESQL: "postgres",
    DBDriver.MYSQL: "root",
    DBDriver.MARIADB: "root",
}

CACHE_DEFAULT_PORTS = {
    CacheDriver.REDIS: 6379,
    CacheDriver.VALKEY: 6379,
    CacheDriver.MEMCACHED: 11211,
}

SQLITE_NON_PATH_NAMES = frozenset({":memory:", ""})

RATE_LIMIT_OFF = frozenset({"", "none", "off", "false"})


def _split_commas(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


class FastAPISettings(BaseSettings):
    model_config = SETTINGS_CONFIG

    app_name: str = "flowlab"
    app_env: AppEnv = AppEnv.LOCAL

    server_host: str = "127.0.0.1"
    server_port: int = 8000

    cors_origins: CommaSeparated | None = Field(default=None)
    cors_origin_regex: str | None = None
    cors_methods: CommaSeparated = ["*"]
    cors_headers: CommaSeparated = ["*"]
    cors_expose_headers: CommaSeparated = []
    cors_credentials: bool = False
    cors_max_age: int = 600

    @property
    def is_local(self) -> bool:
        return self.app_env is AppEnv.LOCAL

    @property
    def is_staging(self) -> bool:
        return self.app_env is AppEnv.STAGING

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    def cors_options(self) -> dict[str, Any]:
        return {
            "allow_origins": self.cors_origins,
            "allow_origin_regex": self.cors_origin_regex,
            "allow_methods": self.cors_methods,
            "allow_headers": self.cors_headers,
            "allow_credentials": self.cors_credentials,
            "expose_headers": self.cors_expose_headers,
            "max_age": self.cors_max_age,
        }

    @field_validator("app_env", mode="before")
    @classmethod
    def _normalize_app_env(cls, value: Any) -> Any:
        return _normalize(value)

    @field_validator("cors_origins", "cors_methods", "cors_headers", "cors_expose_headers", mode="before")
    @classmethod
    def _split_lists(cls, value: Any) -> Any:
        return _split_commas(value)

    @field_validator("cors_origin_regex", mode="before")
    @classmethod
    def _empty_string_is_none(cls, value: Any) -> Any:
        return value or None

    @model_validator(mode="after")
    def _default_cors_origins(self) -> "FastAPISettings":
        if self.cors_origins is None:
            self.cors_origins = ["*"] if self.is_local else []

        return self


class FastMCPSettings(BaseSettings):
    model_config = SETTINGS_CONFIG

    mcp_name: str = "flowlab"
    mcp_path: str = "/mcp"
    mcp_stateless_http: bool = True
    mcp_json_response: bool = True


class TyperSettings(BaseSettings):
    model_config = SETTINGS_CONFIG

    cli_name: str | None = None
    cli_help: str | None = None


class DatabaseSettings(BaseSettings):
    model_config = SETTINGS_CONFIG

    db_driver: DBDriver = DBDriver.SQLITE
    db_name: str | None = None
    db_host: str = "localhost"
    db_port: int | None = None
    db_user: str | None = None
    db_password: str = ""
    db_asyncpg_adapter: bool = False
    db_ensure_always_connected: bool = True
    db_max_concurrent_connections: int = sys.maxsize
    db_acquire_connection_timeout: float = 10.0

    def db_options(self, project_dir: Path) -> dict[str, Any]:
        name = self.db_name or DB_DEFAULT_NAMES.get(self.db_driver, "app")

        if self.db_driver is DBDriver.SQLITE and name not in SQLITE_NON_PATH_NAMES and not name.startswith("file:"):
            path = Path(name)
            name = str(path if path.is_absolute() else project_dir / path)

        options: dict[str, Any] = {
            "name": name,
            "ensure_always_connected": self.db_ensure_always_connected,
            "max_concurrent_connections": self.db_max_concurrent_connections,
            "acquire_connection_timeout": self.db_acquire_connection_timeout,
        }

        if self.db_driver is not DBDriver.SQLITE:
            options |= {
                "host": self.db_host,
                "port": self.db_port,
                "user": self.db_user,
                "password": self.db_password,
            }

        if self.db_driver is DBDriver.POSTGRESQL:
            options["asyncpg_adapter"] = self.db_asyncpg_adapter

        return options

    @field_validator("db_driver", mode="before")
    @classmethod
    def _normalize_db_driver(cls, value: Any) -> Any:
        normalized = _normalize(value)

        return DB_DRIVER_ALIASES.get(normalized, normalized) if isinstance(normalized, str) else normalized

    @field_validator("db_name", "db_user", mode="before")
    @classmethod
    def _empty_string_is_none(cls, value: Any) -> Any:
        return value or None

    @model_validator(mode="after")
    def _default_db_connection(self) -> "DatabaseSettings":
        if self.db_port is None:
            self.db_port = DB_DEFAULT_PORTS.get(self.db_driver)

        if self.db_user is None:
            self.db_user = DB_DEFAULT_USERS.get(self.db_driver)

        return self


class CacheSettings(BaseSettings):
    model_config = SETTINGS_CONFIG

    cache_driver: CacheDriver = CacheDriver.MEMORY
    cache_host: str = "localhost"
    cache_port: int | None = None
    cache_password: str | None = None
    cache_db: int = 0
    cache_table: str = "cache"

    def cache_options(self) -> dict[str, Any]:
        if self.cache_driver is CacheDriver.DATABASE:
            return {"table": self.cache_table}

        options: dict[str, Any] = {"host": self.cache_host, "port": self.cache_port}

        if self.cache_driver is not CacheDriver.MEMCACHED:
            options |= {"db": self.cache_db, "password": self.cache_password}

        return options

    @field_validator("cache_driver", mode="before")
    @classmethod
    def _normalize_cache_driver(cls, value: Any) -> Any:
        return _normalize(value)

    @field_validator("cache_password", mode="before")
    @classmethod
    def _empty_string_is_none(cls, value: Any) -> Any:
        return value or None

    @model_validator(mode="after")
    def _default_cache_connection(self) -> "CacheSettings":
        if self.cache_port is None:
            self.cache_port = CACHE_DEFAULT_PORTS.get(self.cache_driver)

        return self


class QueueSettings(BaseSettings):
    model_config = SETTINGS_CONFIG

    queue_driver: QueueDriver = QueueDriver.SYNC
    queue_name: str = "default"
    queue_host: str = "localhost"
    queue_port: int = 6379
    queue_password: str | None = None
    queue_db: int = 0
    queue_retry_after: float = 90

    def queue_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {"retry_after": self.queue_retry_after}

        if self.queue_driver in (QueueDriver.REDIS, QueueDriver.VALKEY):
            options |= {
                "host": self.queue_host,
                "port": self.queue_port,
                "db": self.queue_db,
                "password": self.queue_password,
            }

        return options

    @field_validator("queue_driver", mode="before")
    @classmethod
    def _normalize_queue_driver(cls, value: Any) -> Any:
        return _normalize(value)

    @field_validator("queue_password", mode="before")
    @classmethod
    def _empty_string_is_none(cls, value: Any) -> Any:
        return value or None


class AuthSettings(BaseSettings):
    model_config = SETTINGS_CONFIG

    jwt_secret: str = ""
    jwt_ttl_minutes: int = 60
    auth_rate_limit: str | None = "5/minute"

    @property
    def jwt_ttl(self) -> timedelta:
        return timedelta(minutes=self.jwt_ttl_minutes)

    @field_validator("jwt_secret")
    @classmethod
    def _require_jwt_secret(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("JWT_SECRET is required when auth is enabled")

        return value

    @field_validator("auth_rate_limit", mode="before")
    @classmethod
    def _parse_rate_limit(cls, value: Any) -> Any:
        if value is None or (isinstance(value, str) and _normalize(value) in RATE_LIMIT_OFF):
            return None

        from flowlab.modules.ratelimit import Limit

        return str(Limit.parse(value)) if isinstance(value, str) else value
