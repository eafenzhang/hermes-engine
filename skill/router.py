"""Skill REST router."""

from __future__ import annotations

from fastapi import APIRouter

from shared.event import bus
from shared.errors import NotFoundError
from shared.models import ApiResponse
from skill.schemas import SkillCreate, SkillMatchRequest

router = APIRouter(prefix="/api/skills", tags=["skills"])

skill_service: "SkillService | None" = None  # noqa: F821


def _get_service():
    assert skill_service is not None, "skill_service not initialized"
    return skill_service


@router.get("")
async def list_skills():
    svc = _get_service()
    items = svc.list()
    return ApiResponse(data=items)


@router.post("/scan")
async def scan_skills():
    svc = _get_service()
    items = svc.scan()
    await bus.publish_domain("skill", "scanned", data={"count": len(items)})
    return ApiResponse(data=items, message=f"Scanned {len(items)} skills")


@router.get("/{name}")
async def get_skill(name: str):
    svc = _get_service()
    skill = svc.get(name)
    if not skill:
        raise NotFoundError(f"Skill '{name}' not found")
    return ApiResponse(data=skill)


@router.post("")
async def create_skill(body: SkillCreate):
    svc = _get_service()
    skill = svc.create(
        name=body.name,
        description=body.description,
        content=body.content,
        tags=body.tags,
        overwrite=body.overwrite,
    )
    await bus.publish_domain("skill", "created", data={"name": body.name})
    return ApiResponse(data=skill, message="Skill created")


@router.delete("/{name}")
async def delete_skill(name: str):
    svc = _get_service()
    if not svc.delete(name):
        raise NotFoundError(f"Skill '{name}' not found")
    await bus.publish_domain("skill", "deleted", data={"name": name})
    return ApiResponse(message="Skill deleted")


@router.post("/match")
async def match_skills(body: SkillMatchRequest):
    svc = _get_service()
    results = svc.search(body.query, body.top_k)
    return ApiResponse(data=results)
