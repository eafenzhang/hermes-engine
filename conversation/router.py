"""Conversation REST router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from conversation.schemas import ConversationCreate, ConversationUpdate, MessageCreate
from shared.dependencies import get_conversation_service
from shared.errors import NotFoundError
from shared.event import bus
from shared.models import ApiResponse, PaginatedResponse

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    service=Depends(get_conversation_service),
):
    items, total = service.list_conversations(limit, offset)
    return PaginatedResponse(data=items, total=total, page=offset // limit + 1, page_size=limit)


@router.post("")
async def create_conversation(body: ConversationCreate, service=Depends(get_conversation_service)):
    conv = service.create(title=body.title, metadata=body.metadata)
    await bus.publish_domain("conversation", "created", data={"conversation_id": conv["id"]})
    return ApiResponse(data=conv, message="Conversation created")


@router.get("/{conv_id}")
async def get_conversation(conv_id: str, service=Depends(get_conversation_service)):
    conv = service.get(conv_id)
    if not conv:
        raise NotFoundError(f"Conversation {conv_id} not found")
    return ApiResponse(data=conv)


@router.put("/{conv_id}")
async def update_conversation(conv_id: str, body: ConversationUpdate, service=Depends(get_conversation_service)):
    conv = service.update(conv_id, title=body.title, metadata=body.metadata)
    if not conv:
        raise NotFoundError(f"Conversation {conv_id} not found")
    await bus.publish_domain("conversation", "updated", data={"conversation_id": conv_id})
    return ApiResponse(data=conv, message="Conversation updated")


@router.get("/{conv_id}/messages")
async def get_messages(
    conv_id: str,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    service=Depends(get_conversation_service),
):
    items, total = service.get_messages(conv_id, limit, offset)
    return PaginatedResponse(data=items, total=total, page=offset // limit + 1, page_size=limit)


@router.post("/{conv_id}/messages")
async def add_message(conv_id: str, body: MessageCreate, service=Depends(get_conversation_service)):
    msg = service.add_message(conv_id, role=body.role, content=body.content, metadata=body.metadata)
    await bus.publish_domain("conversation", "message.added", data={"conversation_id": conv_id, "role": body.role})
    return ApiResponse(data=msg, message="Message added")


@router.delete("/{conv_id}")
async def delete_conversation(conv_id: str, service=Depends(get_conversation_service)):
    if not service.delete(conv_id):
        raise NotFoundError(f"Conversation {conv_id} not found")
    await bus.publish_domain("conversation", "deleted", data={"conversation_id": conv_id})
    return ApiResponse(message="Conversation deleted")
