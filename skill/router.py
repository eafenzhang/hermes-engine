"""Skill REST router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from shared.dependencies import get_skill_service
from shared.errors import NotFoundError, ValidationError
from shared.event import bus
from shared.models import ApiResponse
from skill.patcher import SkillPatcher
from skill.schemas import SkillCreate, SkillMatchRequest, SkillPatchRequest

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


@router.patch("/{name}")
async def patch_skill(
    name: str,
    body: SkillPatchRequest,
    request: Request,
):
    """Surgically patch a skill by replacing old_string with new_string.

    The first occurrence of *old_string* in the skill file is replaced
    by *new_string*.  When ``replace_all`` is true, every occurrence is
    replaced.

    This is the key mechanism for skill self-improvement — the agent can
    refine skills during use without rewriting them from scratch.
    """
    settings = request.app.state.settings
    patcher = SkillPatcher(settings.skills_dir)

    try:
        if body.replace_all:
            result = patcher.patch_all(name, body.old_string, body.new_string)
        else:
            result = patcher.patch(name, body.old_string, body.new_string)

        await bus.publish_domain("skill", "patched", data={"name": name})
        return ApiResponse(data=result, message="Skill patched")
    except NotFoundError:
        raise
    except ValidationError:
        raise


@router.post("/match")
async def match_skills(body: SkillMatchRequest, service=Depends(get_skill_service)):
    # Only scan if the in-memory cache is empty — avoids re-reading all .md
    # files from disk on every single match request.
    if service.loader.count == 0:
        service.scan()
    results = service.search(body.query, body.top_k)
    return ApiResponse(data=results)
