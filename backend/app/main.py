"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import dtd, export, generate, populate, presets, validate
from app.config import PROJECT_ROOT, get_app_settings, get_connection_aliases
from app.services.oracle_client import bootstrap_oracle_client

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

app.include_router(dtd.router, prefix="/api")
app.include_router(generate.router, prefix="/api")
app.include_router(populate.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(presets.router, prefix="/api")
app.include_router(validate.router, prefix="/api")


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
