"""FastAPI dependency-injection container.

Replaces the previous module-level singleton pattern (``router.service = ...``)
with standard FastAPI ``Depends()`` calls, giving each request its own service
instance.  This makes the application testable, traceable, and free of global
mutable state.
"""

from __future__ import annotations

from fastapi import Request

from config.settings import Settings


# ── Settings ────────────────────────────────────────────────────────────

def get_settings(request: Request) -> Settings:
    """Return the application-wide Settings bound to ``app.state``."""
    return request.app.state.settings  # type: ignore[no-any-return]


# ── Agent ───────────────────────────────────────────────────────────────

def get_agent_service(request: Request):
    from agent.engine import AgentEngine
    from agent.service import AgentService

    settings: Settings = request.app.state.settings
    return AgentService(AgentEngine())


# ── Memory ──────────────────────────────────────────────────────────────

def get_memory_service(request: Request):
    from memory.service import MemoryService

    settings: Settings = request.app.state.settings
    return MemoryService(db_path=settings.db_path)


# ── Conversation ────────────────────────────────────────────────────────

def get_conversation_service(request: Request):
    from conversation.service import ConversationService

    settings: Settings = request.app.state.settings
    return ConversationService(db_path=settings.db_path)


# ── Skill ───────────────────────────────────────────────────────────────

def get_skill_service(request: Request):
    from skill.service import SkillService

    settings: Settings = request.app.state.settings
    return SkillService(skills_dir=settings.skills_dir)


# ── Tools ───────────────────────────────────────────────────────────────

def get_tool_service(request: Request):
    from tools.service import ToolService

    return ToolService()


# ── MCP ─────────────────────────────────────────────────────────────────

def get_mcp_service(request: Request):
    from mcp.service import MCPService

    return MCPService()
