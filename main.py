"""Hermes Engine — FastAPI application entry point."""

from __future__ import annotations

import logging
import sys
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

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
    from memory.service import MemoryService
    from memory.router import router as memory_router, memory_service as _mem_svc

    _mem_svc = MemoryService(db_path=settings.db_path)
    app.state.memory_service = _mem_svc
    memory_router.memory_service = _mem_svc  # type: ignore[attr-defined]

    from conversation.service import ConversationService
    from conversation.router import router as conversation_router, conversation_service as _conv_svc

    _conv_svc = ConversationService(db_path=settings.db_path)
    app.state.conversation_service = _conv_svc
    conversation_router.conversation_service = _conv_svc  # type: ignore[attr-defined]

    from agent.engine import AgentEngine
    from agent.service import AgentService
    from agent.router import router as agent_router, agent_service as _agent_svc

    _agent_svc = AgentService(AgentEngine())
    app.state.agent_service = _agent_svc
    agent_router.agent_service = _agent_svc  # type: ignore[attr-defined]

    from skill.service import SkillService
    from skill.router import router as skill_router, skill_service as _skill_svc

    _skill_svc = SkillService(skills_dir=settings.skills_dir)
    app.state.skill_service = _skill_svc
    skill_router.skill_service = _skill_svc  # type: ignore[attr-defined]

    from tools.service import ToolService
    from tools.router import router as tools_router, tool_service as _tool_svc

    _tool_svc = ToolService()
    app.state.tool_service = _tool_svc
    tools_router.tool_service = _tool_svc  # type: ignore[attr-defined]

    from mcp.service import MCPService
    from mcp.router import router as mcp_router, mcp_service as _mcp_svc

    _mcp_svc = MCPService()
    app.state.mcp_service = _mcp_svc
    mcp_router.mcp_service = _mcp_svc  # type: ignore[attr-defined]

    from provider.service import init_providers
    from provider.router import router as provider_router

    init_providers(settings)

    # ── Register routers ─────────────────────────────────────────────────
    app.include_router(provider_router)
    app.include_router(memory_router)
    app.include_router(conversation_router)
    app.include_router(agent_router)
    app.include_router(skill_router)
    app.include_router(tools_router)
    app.include_router(mcp_router)
    app.include_router(provider_router)

    # ── Register built-in tools ───────────────────────────────────────────
    from tools.builtin import register_all as register_builtin_tools
    register_builtin_tools()

    logger.info(
        "Hermes Engine started — data_dir=%s debug=%s providers=%d",
        settings.data_dir,
        settings.debug,
        len(provider_router.registry.list()) if hasattr(provider_router, 'registry') else 0,
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
