"""Hermes Engine — FastAPI application entry point.

Services are wired via FastAPI ``Depends()`` (see ``shared/dependencies.py``).
No module-level singleton injection — every request gets its own service
instance via the standard DI container.
"""

from __future__ import annotations

import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
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
import asyncio as _asyncio

logger = logging.getLogger(__name__)

_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


async def _retry_loop(queue):
    while True:
        try:
            await queue.process()
        except Exception:
            pass
        await _asyncio.sleep(60)


# ═══════════════════════════════════════════════════════════════════════════
# Middleware
# ═══════════════════════════════════════════════════════════════════════════

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject X-Request-ID for tracing.

    Uses the incoming ``X-Request-ID`` header if present, otherwise
    generates a short UUID.  The ID is attached to the request scope
    and returned in the response headers.
    """

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


class AuthMiddleware(BaseHTTPMiddleware):
    """Optional Bearer-token authentication."""

    _PUBLIC_PATHS = frozenset({
        "/api/health", "/api/v1/health",
        "/api/metrics", "/openapi.json", "/docs", "/redoc",
    })

    async def dispatch(self, request: Request, call_next):
        settings: Settings = request.app.state.settings
        if settings.local_mode or request.url.path in self._PUBLIC_PATHS:
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != settings.api_token:
            return JSONResponse(
                status_code=401,
                content={"success": False, "error": "Unauthorized", "code": "AUTH_REQUIRED"},
            )
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with method, path, status, duration, and request ID."""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        req_id = getattr(request.state, "request_id", "-")
        logger.info(
            "%s %s %d %.0fms rid=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            req_id,
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple sliding-window rate limiter (per-IP).

    Configurable via settings:
    - ``rate_limit_enabled`` (default True)
    - ``rate_limit_requests``  (default 300)
    - ``rate_limit_window_s``  (default 60)

    Rate-limited clients receive HTTP 429.
    """

    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self._enabled = settings.rate_limit_enabled
        self._max = settings.rate_limit_requests
        self._window = settings.rate_limit_window_s
        self._counters: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next):
        if not self._enabled:
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Sliding window: keep timestamps within window
        hits = self._counters.get(ip, [])
        hits = [t for t in hits if now - t < self._window]

        if len(hits) >= self._max:
            return JSONResponse(
                status_code=429,
                content={"success": False, "error": "Too many requests", "code": "RATE_LIMITED"},
            )

        hits.append(now)
        self._counters[ip] = hits

        # Periodic cleanup of stale entries (every 1000 requests)
        if len(self._counters) > 10000:
            self._counters = {
                k: v for k, v in self._counters.items()
                if v and now - v[-1] < self._window * 2
            }

        return await call_next(request)


# ═══════════════════════════════════════════════════════════════════════════
# Lifespan
# ═══════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — init resources, register providers, wire routers."""
    settings: Settings = app.state.settings

    # Ensure data directories exist
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.skills_dir.mkdir(parents=True, exist_ok=True)

    # ── Startup validation ────────────────────────────────────────────────
    _validate_startup(settings)

    # ── Register providers ────────────────────────────────────────────────
    from provider.service import init_providers
    init_providers(settings)

    # ── Model cache TTL ───────────────────────────────────────────────────
    from shared.model_cache import model_cache
    model_cache._ttl = settings.model_cache_ttl

    # ── Register routers ──────────────────────────────────────────────────
    _register_routers(app, settings)

    # ── Register tools ────────────────────────────────────────────────────
    from tools.builtin import register_all as register_builtin_tools
    register_builtin_tools()

    if settings.browser_enabled:
        from tools.executor import executor as _tool_executor
        from tools.browser import WEB_FETCH_SCHEMA, WEB_SEARCH_SCHEMA, web_fetch, web_search
        _tool_executor.register("web_fetch", web_fetch, WEB_FETCH_SCHEMA)
        _tool_executor.register("web_search", web_search, WEB_SEARCH_SCHEMA)

    from tools.builtin.execute_command import register_extra_commands
    register_extra_commands(settings.extra_allowed_commands)

    # ── Plugin loader ────────────────────────────────────────────────────
    if settings.plugins_enabled:
        from shared.plugin import PluginLoader
        loader: PluginLoader = PluginLoader(extra_dirs=settings.plugins_dirs)
        names = loader.discover()
        for name in names:
            loader.load(name)
        app.state.plugin_loader = loader

    # ── Cron scheduler ───────────────────────────────────────────────────
    if settings.cron_enabled:
        from shared.scheduler import get_scheduler
        import asyncio as _asyncio
        _asyncio.create_task(get_scheduler().start())

    # ── Data cleaner (background TTL-based pruning) ──────────────────────
    if settings.data_ttl_days > 0:
        from shared.data_cleaner import DataCleaner
        _cleaner = DataCleaner(
            str(settings.db_path), ttl_days=settings.data_ttl_days,
            interval_hours=settings.data_cleaner_interval_hours,
        )
        app.state.data_cleaner = _cleaner
        _asyncio.create_task(_cleaner.start())

    # ── Webhook retry processor ─────────────────────────────────────────
    import gateway.retry as _retry_mod
    _retry_queue = _retry_mod.RetryQueue(str(settings.db_path.parent / "retries.db"))
    app.state.retry_queue = _retry_queue
    _asyncio.create_task(_retry_loop(_retry_queue))

    # ── Hot reload watcher ──────────────────────────────────────────────
    if settings.hot_reload_enabled:
        from shared.hot_reload import watch_env
        _asyncio.create_task(watch_env(lambda: None))  # callback TBD

    # ── Auto-backup (daily) ─────────────────────────────────────────────
    if settings.auto_backup_enabled and settings.cron_enabled:
        from shared.scheduler import get_scheduler as _gs2

        async def _auto_backup():
            from shared.db_maintenance import backup as _bk
            _bk(str(settings.db_path))

        _gs2().add_task("auto-backup", "0 3 * * *", _auto_backup)

    from provider.registry import registry as provider_registry
    logger.info(
        "Hermes Engine started — data_dir=%s debug=%s providers=%d",
        settings.data_dir, settings.debug, provider_registry.count,
    )

    # ── Redis listener ────────────────────────────────────────────────────
    if os.environ.get("HERMES_EVENT_BACKEND", "").strip().lower() == "redis":
        try:
            await bus.start()
        except Exception:
            logger.warning("Failed to start Redis event listener — continuing")

    yield

    # ── Cleanup ───────────────────────────────────────────────────────────
    await _safe_cleanup("MCP bridge", _cleanup_mcp)
    await _safe_cleanup("EventBus", _cleanup_eventbus)
    await _safe_cleanup("SQLite connections", _cleanup_sqlite)
    await _safe_cleanup("Scheduler", _cleanup_scheduler)
    await _safe_cleanup("Plugins", lambda: _cleanup_plugins(app))

    logger.info("Hermes Engine shut down.")


async def _safe_cleanup(name: str, fn):
    try:
        result = fn()
        if hasattr(result, '__await__'):
            await result
    except Exception:
        logger.exception("%s cleanup failed — continuing shutdown", name)


async def _cleanup_mcp():
    from mcp.bridge import bridge as mcp_bridge
    await mcp_bridge.close_all()


async def _cleanup_eventbus():
    await bus.backend.close()


def _cleanup_sqlite():
    from shared.sqlite_base import SQLiteBase
    SQLiteBase.close_all()


def _cleanup_scheduler():
    from shared.scheduler import get_scheduler
    get_scheduler().stop()


def _cleanup_plugins(app):
    _pl = getattr(app.state, "plugin_loader", None)
    if _pl is not None:
        _pl.unload_all()


def _validate_startup(settings: Settings):
    """Warn about common misconfigurations at startup."""
    provider_keys = [
        ("Anthropic", settings.anthropic_api_key),
        ("OpenAI", settings.openai_api_key),
        ("Gemini", settings.gemini_api_key),
        ("DeepSeek", settings.deepseek_api_key),
        ("Moonshot", settings.moonshot_api_key),
        ("Zhipu", settings.zhipu_api_key),
        ("Qwen", settings.qwen_api_key),
        ("MiniMax", settings.minimax_api_key),
    ]
    configured = [name for name, key in provider_keys if key]
    if not configured:
        logger.warning("No AI provider configured — agent chat will fail")
    else:
        logger.info("Configured providers: %s", ", ".join(configured))

    db_dir = settings.db_path.parent
    if not os.access(str(db_dir), os.W_OK):
        logger.warning("Database directory not writable: %s", db_dir)

    if settings.api_token:
        logger.info("API token authentication enabled")
    else:
        logger.info("Running in LOCAL MODE — no authentication required")


def _register_routers(app: FastAPI, settings: Settings):
    """Wire all routers.  Core routers get /api prefix + /api/v1 alias."""
    import agent.router as _agent_mod
    import conversation.router as _conv_mod
    import mcp.router as _mcp_mod
    import memory.router as _mem_mod
    import provider.router as _prov_mod
    import skill.router as _skill_mod
    import tools.router as _tools_mod

    core = [
        (_prov_mod.router, "providers"),
        (_mem_mod.router, "memories"),
        (_conv_mod.router, "conversations"),
        (_agent_mod.router, "agent"),
        (_skill_mod.router, "skills"),
        (_tools_mod.router, "tools"),
        (_mcp_mod.router, "mcp"),
    ]

    for router, _tag in core:
        app.include_router(router)
        # Also register under /api/v1 for versioned access
        app.include_router(router, prefix="/api/v1")

    # OpenAI compat (has its own /v1 prefix)
    import api_compat.router as _api_compat_mod
    app.include_router(_api_compat_mod.router)

    if settings.cron_enabled:
        import shared.scheduler_router as _cron_mod
        app.include_router(_cron_mod.router)
        app.include_router(_cron_mod.router, prefix="/api/v1")

    if settings.gateway_enabled:
        import gateway as _gateway_mod
        from fastapi import APIRouter as _GwRouter
        _gw = _GwRouter(prefix="/api/gateway", tags=["gateway"])

        @_gw.post("/webhook")
        async def _webhook(payload: dict):
            adapter = _gateway_mod.WebhookAdapter()
            result = await adapter.handle_webhook(payload)
            return ApiResponse(data=result)

        app.include_router(_gw)
        app.include_router(_gw, prefix="/api/v1")

    if settings.trajectories_enabled:
        import shared.trajectory_router as _traj_mod
        app.include_router(_traj_mod.router)
        app.include_router(_traj_mod.router, prefix="/api/v1")

    if settings.session_enabled:
        import shared.session_router as _sess_mod
        app.include_router(_sess_mod.router)
        app.include_router(_sess_mod.router, prefix="/api/v1")

    # ── Admin router (API keys, maintenance, audit) ──────────────────────
    if settings.api_keys_enabled:
        from fastapi import APIRouter as _AdminRouter
        _admin = _AdminRouter(prefix="/api/admin", tags=["admin"])
        from shared.api_keys import get_key_store
        from shared.audit import get_audit
        from shared.db_maintenance import backup, vacuum

        _ks = get_key_store(str(settings.db_path.parent / "keys.db"))
        _audit = get_audit(str(settings.db_path.parent / "audit.db"))

        @_admin.post("/keys")
        async def _create_key(data: dict):
            key = _ks.create(
                tenant_id=data.get("tenant_id", "default"),
                name=data.get("name", ""),
                scopes=data.get("scopes"),
            )
            _audit.log("api_key", "created", actor="admin", tenant_id=data.get("tenant_id", "default"))
            return ApiResponse(data={"id": key["key_hash"][:16], "key": key["key"], "scopes": key["scopes"]}, message="Key created")

        @_admin.get("/keys")
        async def _list_keys():
            return ApiResponse(data=_ks.list())

        @_admin.delete("/keys/{key_id}")
        async def _delete_key(key_id: str):
            _ks.delete(key_id)
            _audit.log("api_key", "deleted", actor="admin")
            return ApiResponse(message="Key deleted")

        @_admin.post("/maintenance/backup")
        async def _run_backup():
            r = backup(str(settings.db_path))
            return ApiResponse(data=r)

        @_admin.post("/maintenance/vacuum")
        async def _run_vacuum():
            r = vacuum(str(settings.db_path))
            return ApiResponse(data=r)

        @_admin.get("/audit")
        async def _audit_logs():
            return ApiResponse(data=_audit.query(limit=100))

        app.include_router(_admin)
        app.include_router(_admin, prefix="/api/v1")


# ═══════════════════════════════════════════════════════════════════════════
# App factory
# ═══════════════════════════════════════════════════════════════════════════

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

    # ── Middleware (order matters — Starlette LIFO) ──────────────────────
    # Outermost → Innermost: RequestID → Idempotency → CORS → Tenant →
    #   RateLimit → Auth → Logging → ResponseCache
    app.add_middleware(RequestIDMiddleware)
    if settings.idempotency_enabled:
        from shared.idempotency import IdempotencyHTTPMiddleware
        app.add_middleware(IdempotencyHTTPMiddleware)
    if settings.cors_origins:
        has_wildcard = "*" in settings.cors_origins
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=not has_wildcard,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    from shared.tenant import TenantMiddleware
    app.add_middleware(TenantMiddleware)
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    if settings.response_cache_enabled:
        from shared.response_cache import CacheMiddleware
        app.add_middleware(CacheMiddleware)

    # ── Exception handlers ───────────────────────────────────────────────
    app.add_exception_handler(ServiceError, service_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(400, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(422, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(500, unhandled_exception_handler)  # type: ignore[arg-type]

    # ── Health check (deep) ──────────────────────────────────────────────
    @app.get("/api/health")
    @app.get("/api/v1/health")
    async def health():
        return await _deep_health_check(settings)

    # ── Redirect /api → /api/v1 for versioned access ─────────────────────
    @app.get("/api")
    async def api_index():
        return JSONResponse({
            "name": "Hermes Engine",
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/api/health",
        })

    # ── WebSocket event bus ──────────────────────────────────────────────
    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
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


async def _deep_health_check(settings: Settings) -> HealthResponse:
    """Return enriched health status with actual provider + DB state."""
    from provider.registry import registry as prov_reg
    from shared.sqlite_base import SQLiteBase

    providers_ok = 0
    providers_total = prov_reg.count
    provider_names: list[str] = []

    for p_info in prov_reg.list():
        name = p_info["name"]
        provider_names.append(name)
        provider = prov_reg.get(name)
        if provider:
            try:
                if await provider.check_connectivity():
                    providers_ok += 1
            except Exception:
                pass

    # DB connectivity
    db_ok = False
    try:
        import sqlite3
        conn = sqlite3.connect(str(settings.db_path))
        conn.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception:
        pass

    status = "ok" if (db_ok and (providers_total == 0 or providers_ok > 0)) else "degraded"
    if not db_ok and providers_ok == 0:
        status = "unhealthy"

    return HealthResponse(
        status=status,
        version="0.1.0",
        providers=providers_ok,
        conversations=0,  # populated below if DB ok
        skills=0,
        memories=0,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════

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
        timeout_graceful_shutdown=settings.graceful_shutdown_timeout,
        timeout_keep_alive=settings.keep_alive_timeout,
        backlog=settings.backlog,
    )


if __name__ == "__main__":
    main()
