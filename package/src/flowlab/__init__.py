from importlib.metadata import PackageNotFoundError, version

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Cookie,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    Security,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastmcp.dependencies import Depends as MCPDepends

from flowlab._cache import Cache, get_cache
from flowlab._database import DB, INTEGRITY_ERRORS, get_db
from flowlab._exceptions import (
    AuthNotEnabled,
    FlowLabAlreadyInitialized,
    FlowLabError,
    FlowLabNotInitialized,
    NotConnected,
    SchemaMismatch,
)
from flowlab._flowlab import FlowLab
from flowlab._module import Module
from flowlab._queue import get_queue
from flowlab._routing import Command, CommandRouter, MCPRouter
from flowlab._settings import (
    AppEnv,
    AuthSettings,
    CacheDriver,
    CacheSettings,
    DatabaseSettings,
    DBDriver,
    FastAPISettings,
    FastMCPSettings,
    QueueDriver,
    QueueSettings,
    TyperSettings,
)
from flowlab._state import get_app

try:
    __version__ = version("flowlab")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without metadata
    __version__ = "0.0.0"

__all__ = [
    "DB",
    "INTEGRITY_ERRORS",
    "APIRouter",
    "AppEnv",
    "AuthNotEnabled",
    "AuthSettings",
    "BackgroundTasks",
    "Body",
    "Cache",
    "CacheDriver",
    "CacheSettings",
    "Command",
    "CommandRouter",
    "Cookie",
    "DBDriver",
    "DatabaseSettings",
    "Depends",
    "FastAPISettings",
    "FastMCPSettings",
    "File",
    "FlowLab",
    "FlowLabAlreadyInitialized",
    "FlowLabError",
    "FlowLabNotInitialized",
    "Form",
    "HTTPException",
    "Header",
    "MCPDepends",
    "MCPRouter",
    "Module",
    "NotConnected",
    "Path",
    "Query",
    "QueueDriver",
    "QueueSettings",
    "Request",
    "Response",
    "SchemaMismatch",
    "Security",
    "TyperSettings",
    "UploadFile",
    "WebSocket",
    "WebSocketDisconnect",
    "__version__",
    "get_app",
    "get_cache",
    "get_db",
    "get_queue",
    "status",
]
