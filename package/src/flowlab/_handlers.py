import logging
import traceback

from fastapi import Request, status
from fastapi.responses import JSONResponse

from flowlab._database import DB
from flowlab._state import get_app

logger = logging.getLogger("flowlab")


def handle_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception while processing %s %s", request.method, request.url.path)

    if get_app().fastapi_settings.is_production:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    tb = traceback.TracebackException.from_exception(exc)
    last = tb.stack[-1] if tb.stack else None

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": type(exc).__qualname__,
            "detail": str(exc),
            "file": last.filename if last else None,
            "line": last.lineno if last else None,
            "stacktrace": [
                {
                    "file": frame.filename,
                    "line": frame.lineno,
                    "function": frame.name,
                }
                for frame in tb.stack
            ],
        },
    )


def health(db: DB) -> JSONResponse:
    try:
        db.list_tables()
        healthy = True
    except Exception:
        logger.exception("Health check failed: database is not reachable")
        healthy = False

    return JSONResponse(
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"database": healthy},
    )
