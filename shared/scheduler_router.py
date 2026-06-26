"""Scheduler REST router — cron task CRUD + NL parsing."""

from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter

from shared.models import ApiResponse
from shared.scheduler import get_scheduler, parse_nl_cron


class CronTaskCreate(BaseModel):
    name: str = ""  # auto-generated when empty
    cron: str = "0 0 * * *"
    prompt: str = Field(..., min_length=1)


class CronParseRequest(BaseModel):
    text: str = Field(..., min_length=1)


router = APIRouter(prefix="/api/cron", tags=["cron"])


@router.get("")
async def list_tasks():
    return ApiResponse(data=get_scheduler().list_tasks())


@router.post("")
async def create_task(body: CronTaskCreate):
    """Register a cron task."""
    name = body.name or f"task-{len(get_scheduler().list_tasks())}"

    async def fire():
        from agent.engine import AgentEngine
        engine = AgentEngine()
        await engine.run_turn(
            messages=[{"role": "user", "content": body.prompt}],
        )

    task = get_scheduler().add_task(name, body.cron, fire)
    return ApiResponse(data=task, message=f"Cron task '{name}' registered")


@router.post("/parse")
async def parse_cron(body: CronParseRequest):
    """Parse natural language into a cron expression."""
    cron = await parse_nl_cron(body.text)
    return ApiResponse(data={"cron": cron}, message="Parsed" if cron else "Parse failed")


@router.delete("/{name}")
async def delete_task(name: str):
    if get_scheduler().remove_task(name):
        return ApiResponse(message=f"Cron task '{name}' removed")
    return ApiResponse(message=f"Cron task '{name}' not found")
