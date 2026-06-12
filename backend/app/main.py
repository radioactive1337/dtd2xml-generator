"""FastAPI application entry point."""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import db, dtd, export, fill, generate, mapping_presets, presets, validate
from app.config import PROJECT_ROOT, get_app_settings, get_connection_aliases
from app.core.logging_config import setup_logging
from app.services.oracle_client import bootstrap_oracle_client

setup_logging()
logger = logging.getLogger(__name__)

bootstrap_oracle_client()

app = FastAPI(
    title="QA XML Generator",
    description="Local QA tool for generating XML from DTD schemas",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(db.router, prefix="/api")
app.include_router(dtd.router, prefix="/api")
app.include_router(generate.router, prefix="/api")
app.include_router(fill.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(presets.router, prefix="/api")
app.include_router(mapping_presets.router, prefix="/api")
app.include_router(validate.router, prefix="/api")


@app.exception_handler(Exception)
async def log_exceptions(request: Request, exc: Exception) -> JSONResponse:
    """Log server errors with request context before returning a response."""
    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        if exc.status_code >= 500:
            logger.error(
                "HTTP %s %s %s -> %s",
                request.method,
                request.url.path,
                exc.status_code,
                exc.detail,
            )
        elif exc.status_code >= 400:
            logger.warning(
                "HTTP %s %s %s -> %s",
                request.method,
                request.url.path,
                exc.status_code,
                exc.detail,
            )
        return await http_exception_handler(request, exc)

    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config/aliases")
async def config_aliases() -> dict[str, list[str]]:
    """Return connection aliases only — no secrets."""
    return get_connection_aliases()


# Serve built Vue frontend in production
_frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    settings = get_app_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
