"""Memory REST router."""

from __future__ import annotations

from fastapi import APIRouter, Query

from memory.schemas import MemoryCreate, MemoryUpdate
from shared.event import bus
from shared.models import ApiResponse, PaginatedResponse

router = APIRouter(prefix="/api/memories", tags=["memories"])

# Set by app lifespan
memory_service: "MemoryService | None" = None  # noqa: F821


def _get_service():
    assert memory_service is not None, "memory_service not initialized"
    return memory_service


@router.get("")
async def list_memories(
    scope: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    svc = _get_service()
    items, total = svc.list_memories(scope, limit, offset)
    return PaginatedResponse(data=items, total=total, page=offset // limit + 1, page_size=limit)


@router.get("/search")
async def search_memories(
    q: str,
    scope: str | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
):
    svc = _get_service()
    items, total = svc.search(q, scope, limit, offset)
    return PaginatedResponse(data=items, total=total, query=q, page=offset // limit + 1, page_size=limit)


@router.post("")
async def create_memory(body: MemoryCreate):
    svc = _get_service()
    mem = svc.create_memory(
        content=body.content,
        summary=body.summary,
        source=body.source,
        scope=body.scope,
        importance=body.importance,
        tags=body.tags,
    )
    await bus.publish_domain("memory", "created", data={"memory_id": mem["id"]})
    return ApiResponse(data=mem, message="Memory created")


@router.get("/{mem_id}")
async def get_memory(mem_id: str):
    svc = _get_service()
    mem = svc.get_memory(mem_id)
    if not mem:
        from shared.errors import NotFoundError
        raise NotFoundError(f"Memory {mem_id} not found")
    return ApiResponse(data=mem)


@router.put("/{mem_id}")
async def update_memory(mem_id: str, body: MemoryUpdate):
    svc = _get_service()
    mem = svc.update_memory(mem_id, **body.model_dump(exclude_none=True))
    if not mem:
        from shared.errors import NotFoundError
        raise NotFoundError(f"Memory {mem_id} not found")
    await bus.publish_domain("memory", "updated", data={"memory_id": mem_id})
    return ApiResponse(data=mem, message="Memory updated")


@router.delete("/{mem_id}")
async def delete_memory(mem_id: str):
    svc = _get_service()
    if not svc.delete_memory(mem_id):
        from shared.errors import NotFoundError
        raise NotFoundError(f"Memory {mem_id} not found")
    await bus.publish_domain("memory", "deleted", data={"memory_id": mem_id})
    return ApiResponse(message="Memory deleted")


@router.get("/curator/state")
async def curator_state():
    svc = _get_service()
    return ApiResponse(data=svc.get_curator_state())


@router.post("/curator/run")
async def run_curator():
    svc = _get_service()
    report = await svc.run_curator()
    await bus.publish_domain("memory", "curator.run", data=report)
    return ApiResponse(data=report, message="Curator run complete")
