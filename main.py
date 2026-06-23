"""Hermes Engine — FastAPI application entry point."""

from __future__ import annotations

import logging
import sys
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — init resources, register providers, wire domains."""
    settings: Settings = app.state.settings

    # Ensure data directories exist
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.skills_dir.mkdir(parents=True, exist_ok=True)

    # ── Initialize services ──────────────────────────────────────────────
    import memory.router as _mem_router_mod
    from memory.service import MemoryService

    _mem_router_mod.memory_service = MemoryService(db_path=settings.db_path)

    import conversation.router as _conv_router_mod
    from conversation.service import ConversationService

    _conv_router_mod.conversation_service = ConversationService(db_path=settings.db_path)

    import agent.router as _agent_router_mod
    from agent.engine import AgentEngine
    from agent.service import AgentService

    _agent_router_mod.agent_service = AgentService(AgentEngine())

    import skill.router as _skill_router_mod
    from skill.service import SkillService

    _skill_router_mod.skill_service = SkillService(skills_dir=settings.skills_dir)

    import tools.router as _tools_router_mod
    from tools.service import ToolService

    _tools_router_mod.tool_service = ToolService()

    import mcp.router as _mcp_router_mod
    from mcp.service import MCPService

    _mcp_router_mod.mcp_service = MCPService()

    from provider.service import init_providers
    import provider.router as _provider_router_mod

    init_providers(settings)

    # ── Register routers ─────────────────────────────────────────────────
    from provider.registry import registry as provider_registry

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

    logger.info(
        "Hermes Engine started — data_dir=%s debug=%s providers=%d",
        settings.data_dir,
        settings.debug,
        provider_registry.count,
    )
    yield

    # ── Cleanup ──────────────────────────────────────────────────────────
    from mcp.bridge import bridge as mcp_bridge
    await mcp_bridge.close_all()
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
                # Keep connection alive — receive ping/pong
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
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="debug" if settings.debug else "info",
    )


if __name__ == "__main__":
    main()
