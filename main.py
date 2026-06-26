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
from shared.models import ApiResponse, HealthResponse

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

    # ── Initialise model cache TTL ────────────────────────────────────────
    from shared.model_cache import model_cache
    model_cache._ttl = settings.model_cache_ttl

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

    # ── Register OpenAI-compatible endpoint ────────────────────────────────
    import api_compat.router as _api_compat_router_mod
    app.include_router(_api_compat_router_mod.router)

    # ── Register built-in tools ───────────────────────────────────────────
    from tools.builtin import register_all as register_builtin_tools
    register_builtin_tools()

    # ── Register browser tools ──────────────────────────────────────────
    if settings.browser_enabled:
        from tools.executor import executor as _tool_executor
        from tools.browser import WEB_FETCH_SCHEMA, WEB_SEARCH_SCHEMA, web_fetch, web_search
        _tool_executor.register("web_fetch", web_fetch, WEB_FETCH_SCHEMA)
        _tool_executor.register("web_search", web_search, WEB_SEARCH_SCHEMA)

    # ── Register extra allowed commands from settings ────────────────────
    from tools.builtin.execute_command import register_extra_commands
    register_extra_commands(settings.extra_allowed_commands)

    # ── Register scheduler, gateway, trajectory routers ─────────────────
    if settings.cron_enabled:
        import shared.scheduler_router as _cron_mod
        app.include_router(_cron_mod.router)

    if settings.gateway_enabled:
        import gateway as _gateway_mod
        from fastapi import APIRouter as _GwRouter
        # Gateway webhook endpoint
        _gw = _GwRouter(prefix="/api/gateway", tags=["gateway"])

        @_gw.post("/webhook")
        async def _webhook(payload: dict):
            adapter = _gateway_mod.WebhookAdapter()
            result = await adapter.handle_webhook(payload)
            return ApiResponse(data=result)

        app.include_router(_gw)

    if settings.trajectories_enabled:
        import shared.trajectory_router as _traj_mod
        app.include_router(_traj_mod.router)

    # ── Session router (stateful multi-turn) ────────────────────────────
    if settings.session_enabled:
        import shared.session_router as _sess_mod
        app.include_router(_sess_mod.router)

    # ── Plugin loader ────────────────────────────────────────────────────
    if settings.plugins_enabled:
        from shared.plugin import PluginLoader
        loader: PluginLoader = PluginLoader(extra_dirs=settings.plugins_dirs)
        names = loader.discover()
        for name in names:
            loader.load(name)
        app.state.plugin_loader = loader

    # ── Start cron scheduler ────────────────────────────────────────────
    if settings.cron_enabled:
        from shared.scheduler import get_scheduler
        import asyncio as _asyncio
        _scheduler_task = _asyncio.create_task(get_scheduler().start())

    from provider.registry import registry as provider_registry
    logger.info(
        "Hermes Engine started — data_dir=%s debug=%s providers=%d",
        settings.data_dir,
        settings.debug,
        provider_registry.count,
    )

    # ── Start Redis event bus listener if backend is redis ────────────
    import os as _os
    if _os.environ.get("HERMES_EVENT_BACKEND", "").strip().lower() == "redis":
        try:
            await bus.start()
        except Exception:
            logger.warning("Failed to start Redis event listener — continuing")

    yield

    # ── Cleanup (guaranteed to run, even on exception) ─────────────────────
    try:
        from mcp.bridge import bridge as mcp_bridge
        await mcp_bridge.close_all()
    except Exception:
        logger.exception("MCP bridge cleanup failed — continuing shutdown")

    try:
        await bus.backend.close()
    except Exception:
        logger.exception("EventBus backend cleanup failed — continuing shutdown")

    try:
        from shared.sqlite_base import SQLiteBase
        SQLiteBase.close_all()
    except Exception:
        logger.exception("SQLite connection cleanup failed — continuing shutdown")

    try:
        from shared.scheduler import get_scheduler
        get_scheduler().stop()
    except Exception:
        logger.exception("Scheduler stop failed — continuing shutdown")

    try:
        _pl = getattr(app.state, "plugin_loader", None)
        if _pl is not None:
            _pl.unload_all()
    except Exception:
        logger.exception("Plugin unload failed — continuing shutdown")

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
        # Per the CORS spec, ``Access-Control-Allow-Origin: *`` is incompatible
        # with ``Access-Control-Allow-Credentials: true``.  Browsers reject the
        # response when both are present.  We only enable credentials when a
        # concrete (non-wildcard) origin list is configured.
        has_wildcard = "*" in settings.cors_origins
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=not has_wildcard,
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
        # Optional token auth via query param: /ws?token=my-secret
        if not settings.local_mode:
            token = ws.query_params.get("token", "")
            if not token or token != settings.api_token:
                await ws.close(code=4001, reason="Unauthorized")
                return

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
