"""Hermes Engine — FastAPI application entry point.

Services are wired via FastAPI ``Depends()`` (see ``shared/dependencies.py``).
No module-level singleton injection — every request gets its own service
instance via the standard DI container.
"""

from __future__ import annotations

import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from config.settings import Settings
from shared.errors import (
    ServiceError,
    http_exception_handler,
    service_error_handler,
    unhandled_exception_handler,
)
from shared.event import bus
from shared.models import HealthResponse

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Optional Bearer-token authentication.

    Authentication is controlled by ``settings.local_mode`` (derived from
    ``HERMES_API_TOKEN``): when no token is configured the engine runs in
    local mode and every request is allowed — intended for desktop embedding.
    When a token *is* set, every request (except ``/api/health`` and the
    WebSocket ``/ws``) must include ``Authorization: Bearer <token>``.
    """

    _PUBLIC_PATHS = frozenset({"/api/health"})

    async def dispatch(self, request: Request, call_next):
        settings: Settings = request.app.state.settings
        # Local mode (no API token configured) skips authentication entirely.
        # Public health checks are always exempt.
        if settings.local_mode or request.url.path in self._PUBLIC_PATHS:
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != settings.api_token:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={"success": False, "error": "Unauthorized", "code": "AUTH_REQUIRED"},
            )
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with method, path, status, and duration."""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        logger.info(
            "%s %s %d %.0fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — init resources, register providers, wire routers."""
    settings: Settings = app.state.settings

    # Ensure data directories exist
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.skills_dir.mkdir(parents=True, exist_ok=True)

    # ── Register providers ────────────────────────────────────────────────
    from provider.service import init_providers
    init_providers(settings)

    # ── Register routers (services are injected per-request via Depends) ──
    import agent.router as _agent_router_mod
    import conversation.router as _conv_router_mod
    import mcp.router as _mcp_router_mod
    import memory.router as _mem_router_mod
    import provider.router as _provider_router_mod
    import skill.router as _skill_router_mod
    import tools.router as _tools_router_mod

    app.include_router(_provider_router_mod.router)
    app.include_router(_mem_router_mod.router)
    app.include_router(_conv_router_mod.router)
    app.include_router(_agent_router_mod.router)
    app.include_router(_skill_router_mod.router)
    app.include_router(_tools_router_mod.router)
    app.include_router(_mcp_router_mod.router)

    # ── Register built-in tools ───────────────────────────────────────────
    from tools.builtin import register_all as register_builtin_tools
    register_builtin_tools()

    # ── Register extra allowed commands from settings ────────────────────
    from tools.builtin.execute_command import register_extra_commands
    register_extra_commands(settings.extra_allowed_commands)

    from provider.registry import registry as provider_registry
    logger.info(
        "Hermes Engine started — data_dir=%s debug=%s providers=%d",
        settings.data_dir,
        settings.debug,
        provider_registry.count,
    )
    yield

    # ── Cleanup (guaranteed to run, even on exception) ─────────────────────
    try:
        from mcp.bridge import bridge as mcp_bridge
        await mcp_bridge.close_all()
    except Exception:
        logger.exception("MCP bridge cleanup failed — continuing shutdown")

    try:
        from shared.event import bus
        await bus.backend.close()
    except Exception:
        logger.exception("EventBus backend cleanup failed — continuing shutdown")

    logger.info("Hermes Engine shut down.")


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()

    app = FastAPI(
        title="Hermes Engine",
        version="0.1.0",
        description="Feature-based FastAPI backend exposing Hermes Agent core capabilities",
        lifespan=lifespan,
    )
    app.state.settings = settings

    # ── Observability ────────────────────────────────────────────────────
    from shared.observability import setup_metrics, setup_tracing
    setup_metrics(app)
    setup_tracing(app)

    # ── CORS ──────────────────────────────────────────────────────────────
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # ── Middleware ────────────────────────────────────────────────────────
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    # ── Exception handlers ───────────────────────────────────────────────
    app.add_exception_handler(ServiceError, service_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(422, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(500, unhandled_exception_handler)  # type: ignore[arg-type]

    # ── Health check ──────────────────────────────────────────────────────
    @app.get("/api/health")
    async def health():
        return HealthResponse(status="ok", version="0.1.0")

    # ── WebSocket event bus ──────────────────────────────────────────────
    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        conn_id = str(uuid.uuid4())
        bus.subscribe_ws(conn_id, ws)
        try:
            while True:
                data = await ws.receive_text()
                if data == "ping":
                    await ws.send_text("pong")
        except WebSocketDisconnect:
            pass
        finally:
            bus.unsubscribe_ws(conn_id)

    return app


def main() -> None:
    settings = Settings()
    from shared.observability import setup_logging
    setup_logging(level=logging.DEBUG if settings.debug else logging.INFO)

    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="debug" if settings.debug else "info",
        timeout_graceful_shutdown=10,
    )


if __name__ == "__main__":
    main()
