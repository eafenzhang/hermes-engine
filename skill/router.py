"""Skill REST router."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from shared.dependencies import get_skill_service
from shared.errors import NotFoundError
from shared.event import bus
from shared.models import ApiResponse
from skill.schemas import SkillCreate, SkillMatchRequest

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
async def list_skills(service=Depends(get_skill_service)):
    return ApiResponse(data=service.list_all())


@router.post("/scan")
async def scan_skills(service=Depends(get_skill_service)):
    items = service.scan()
    await bus.publish_domain("skill", "scanned", data={"count": len(items)})
    return ApiResponse(data=items, message=f"Scanned {len(items)} skills")


@router.get("/{name}")
async def get_skill(name: str, service=Depends(get_skill_service)):
    skill = service.get(name)
    if not skill:
        raise NotFoundError(f"Skill '{name}' not found")
    return ApiResponse(data=skill)


@router.post("")
async def create_skill(body: SkillCreate, service=Depends(get_skill_service)):
    skill = service.create(
        name=body.name,
        description=body.description,
        content=body.content,
        tags=body.tags,
        overwrite=body.overwrite,
    )
    await bus.publish_domain("skill", "created", data={"name": body.name})
    return ApiResponse(data=skill, message="Skill created")


@router.delete("/{name}")
async def delete_skill(name: str, service=Depends(get_skill_service)):
    if not service.delete(name):
        raise NotFoundError(f"Skill '{name}' not found")
    await bus.publish_domain("skill", "deleted", data={"name": name})
    return ApiResponse(message="Skill deleted")


@router.post("/match")
async def match_skills(body: SkillMatchRequest, service=Depends(get_skill_service)):
    # Ensure the in-memory cache is up to date (each request gets a fresh
    # SkillLoader, so we scan before searching).
    service.scan()
    results = service.search(body.query, body.top_k)
    return ApiResponse(data=results)
