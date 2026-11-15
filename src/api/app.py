"""
src/api/app.py
~~~~~~~~~~~~~~
FastAPI application factory for Market Insight Engine.

Usage
-----
    # From the MIE_V0.10/ directory:
    uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import configure_logging, get_settings
from core.exceptions import InvalidRequestError, MIEError, NotFoundError

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Lifespan (startup / shutdown)
# --------------------------------------------------------------------------- #


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise resources on startup; clean up on shutdown."""
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        log_dir=settings.data_root.parent / "logs",
    )
    settings.ensure_data_dirs()
    logger.info(
        "Market Insight Engine starting",
        extra={"env": settings.env, "data_root": str(settings.data_root)},
    )

    yield  # ← application runs here

    logger.info("Market Insight Engine shutting down cleanly.")


# --------------------------------------------------------------------------- #
# Application factory
# --------------------------------------------------------------------------- #


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Market Insight Engine API",
        version="0.10.0",
        description=(
            "Local-first stock market data analysis platform. "
            "All predictions are for research reference only and do NOT "
            "constitute investment advice."
        ),
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    # ── CORS (localhost only by default) ───────────────────────────────── #
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # ── Global exception handlers ──────────────────────────────────────── #
    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"code": exc.code, "detail": exc.message})

    @app.exception_handler(InvalidRequestError)
    async def invalid_request_handler(request: Request, exc: InvalidRequestError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"code": exc.code, "detail": exc.message})

    @app.exception_handler(MIEError)
    async def generic_mie_handler(request: Request, exc: MIEError) -> JSONResponse:
        logger.error("Unhandled MIEError: %s", exc)
        return JSONResponse(status_code=500, content={"code": exc.code, "detail": exc.message})

    # ── Routers ────────────────────────────────────────────────────────── #
    from api.v1.acquisition import router as acquisition_router  # noqa: PLC0415
    from api.v1.analysis import router as analysis_router  # noqa: PLC0415
    from api.v1.market import router as market_router  # noqa: PLC0415
    from api.v1.prediction import router as prediction_router  # noqa: PLC0415
    from api.v1.system import router as system_router  # noqa: PLC0415

    app.include_router(system_router, prefix="/api/v1")
    app.include_router(market_router, prefix="/api/v1")
    app.include_router(analysis_router, prefix="/api/v1")
    app.include_router(prediction_router, prefix="/api/v1")
    app.include_router(acquisition_router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "Market Insight Engine", "version": "0.10.0", "status": "ok"}

    web_dist = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
    if web_dist.exists():
        from fastapi.staticfiles import StaticFiles  # noqa: PLC0415

        app.mount("/ui", StaticFiles(directory=str(web_dist), html=True), name="ui")

    return app


app = create_app()


def run() -> None:
    """Entrypoint to launch API server bound to local host (default: 127.0.0.1)."""
    import uvicorn

    settings = get_settings()
    logger.info("Binding API to %s:%d", settings.host, settings.port)
    uvicorn.run(
        "api.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
    )


if __name__ == "__main__":
    run()
