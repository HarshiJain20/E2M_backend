"""Turn data-service failures into clear responses instead of bare 500s."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.repositories.base import RepositoryError
from app.services.storage import StorageError

logger = logging.getLogger(__name__)

DATA_UNAVAILABLE = "The server can't reach its database right now. Try again in a moment."
STORAGE_UNAVAILABLE = "Photo storage is unavailable right now. Try again in a moment."
SESSION_EXPIRED = "Your session has expired. Sign in again."
SCHEMA_MISSING = "The database isn't set up yet. Run supabase/schema.sql in the Supabase SQL Editor."
MISSING_TABLE_CODES = {"PGRST205", "42P01"}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RepositoryError)
    async def repository_error(request: Request, exc: RepositoryError) -> JSONResponse:
        logger.error("Data error on %s %s: %s", request.method, request.url.path, exc)
        if exc.code in MISSING_TABLE_CODES:
            logger.error("E2M tables are missing. Run E2M_backend/supabase/schema.sql in Supabase → SQL Editor.")
            return JSONResponse(status_code=503, content={"detail": SCHEMA_MISSING})
        if exc.status_code == 401:
            return JSONResponse(status_code=401, content={"detail": SESSION_EXPIRED})
        return JSONResponse(status_code=503, content={"detail": DATA_UNAVAILABLE})

    @app.exception_handler(StorageError)
    async def storage_error(request: Request, exc: StorageError) -> JSONResponse:
        logger.error("Storage error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(status_code=503, content={"detail": STORAGE_UNAVAILABLE})
