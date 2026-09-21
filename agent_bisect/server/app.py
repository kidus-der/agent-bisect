"""`create_app(settings)`: the FastAPI app factory backing `bisect serve`.

Wires one `DashboardRepository` (fixture or real, per `settings.data_source`)
onto `app.state`, every `/api/*` router, security headers, a narrow CORS
allowlist for the Vite dev server, and -- last, so it can never shadow an
API route -- the built dashboard's static-file/SPA fallback.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from agent_bisect.server import (
    routes_benchmark,
    routes_live,
    routes_meta,
    routes_overview,
    routes_pr,
    routes_runs,
)
from agent_bisect.server.fixture_repository import FixtureRepository
from agent_bisect.server.real_repository import RealRepository
from agent_bisect.server.repository import DashboardRepository
from agent_bisect.server.schemas_common import Envelope, ErrorInfo, ResponseMeta
from agent_bisect.server.security_headers import SecurityHeadersMiddleware
from agent_bisect.server.settings import ServerSettings
from agent_bisect.server.static import register_static


def _build_repository(settings: ServerSettings) -> DashboardRepository:
    if settings.data_source == "fixture":
        return FixtureRepository(seed=settings.fixture_seed)
    return RealRepository(
        runs_dir=settings.runs_dir,
        data_dir=settings.data_dir,
        models_path=settings.models_path,
    )


def _fallback_meta(settings: ServerSettings) -> ResponseMeta:
    return ResponseMeta(
        simulated=settings.data_source == "fixture", data_source=settings.data_source
    )


def create_app(settings: ServerSettings | None = None) -> FastAPI:
    settings = settings or ServerSettings()
    app = FastAPI(title="Bisect dashboard API", version="0.1.0")
    app.state.repository = _build_repository(settings)
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # `deps.not_found` already builds `exc.detail` as a full envelope dict;
        # a bare string detail (FastAPI's own 404 for an unmatched route, etc.)
        # is wrapped the same shape here so every error response has one shape.
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        envelope = Envelope(
            success=False,
            data=None,
            error=ErrorInfo(code=str(exc.status_code), message=str(exc.detail)),
            meta=_fallback_meta(settings),
        )
        return JSONResponse(status_code=exc.status_code, content=envelope.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        envelope = Envelope(
            success=False,
            data=None,
            error=ErrorInfo(code="422", message="request validation failed"),
            meta=_fallback_meta(settings),
        )
        return JSONResponse(status_code=422, content=envelope.model_dump(mode="json"))

    for router in (
        routes_meta.router,
        routes_overview.router,
        routes_runs.router,
        routes_benchmark.router,
        routes_live.router,
        routes_pr.router,
    ):
        app.include_router(router)

    register_static(app)
    return app
