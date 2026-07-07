"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from app.api.routes import config, db, dtd, export, fill, generate, mapping_presets, presets, validate, xml_compare, xml_library
from app.auth import routes as auth
from app.auth.sessions import get_current_user, install_session_middleware
from app.auth.users import init_user_db
from app.config import PROJECT_ROOT, ensure_app_config, get_app_settings
from app.core.logging_config import setup_logging
from app.services.db_service import close_db_pools
from app.services.llm_service import close_llm_http_client
from app.services.oracle_client import bootstrap_oracle_client
from app.user_context import UserContext


class SPAStaticFiles(StaticFiles):
    """Static files with index.html fallback for Vue Router history mode."""

    async def get_response(self, path: str, scope: Scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            if scope["method"] not in {"GET", "HEAD"}:
                raise
            if "." in path.rsplit("/", 1)[-1]:
                raise
            return await super().get_response("index.html", scope)

setup_logging()
logger = logging.getLogger(__name__)

ensure_app_config()
bootstrap_oracle_client()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_user_db()
    logger.info("User database initialized")
    yield
    await close_db_pools()
    await close_llm_http_client()


app = FastAPI(
    title="QA XML Generator",
    description="Local QA tool for generating XML from DTD schemas",
    version="0.3.0",
    lifespan=lifespan,
)

install_session_middleware(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(db.router, prefix="/api")
app.include_router(dtd.router, prefix="/api")
app.include_router(generate.router, prefix="/api")
app.include_router(fill.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(presets.router, prefix="/api")
app.include_router(mapping_presets.router, prefix="/api")
app.include_router(xml_library.router, prefix="/api")
app.include_router(xml_compare.router, prefix="/api")
app.include_router(validate.router, prefix="/api")


@app.exception_handler(Exception)
async def log_exceptions(request: Request, exc: Exception) -> JSONResponse:
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
async def config_aliases_legacy(
    user: UserContext = Depends(get_current_user),
) -> dict[str, list[str] | str | None]:
    from app.config import get_connection_aliases

    return get_connection_aliases(user)


_frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", SPAStaticFiles(directory=str(_frontend_dist), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    settings = get_app_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
