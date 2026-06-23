"""Provider REST router."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from provider.registry import registry
from provider.schemas import ChatRequest, ProviderListResponse
from shared.errors import NotFoundError, ServiceError
from shared.models import ApiResponse

router = APIRouter(prefix="/api/providers", tags=["providers"])

_DEFAULT_MODEL = "claude-sonnet-4-20250514"


@router.get("", response_model=ProviderListResponse)
async def list_providers():
    return ProviderListResponse(data=registry.list())


@router.post("/chat")
async def chat(request: ChatRequest):
    """Send a chat completion request to the specified provider."""
    provider = registry.get(request.provider)
    if not provider:
        raise NotFoundError(f"Provider '{request.provider}' not found")

    messages = request.messages
    model = request.model or _DEFAULT_MODEL

    try:
        if request.stream:
            return StreamingResponse(
                provider.chat_completion_stream(
                    messages=messages,
                    model=model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    tools=request.tools,
                ),
                media_type="text/event-stream",
            )
        else:
            result = await provider.chat_completion(
                messages=messages,
                model=model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                tools=request.tools,
            )
            return ApiResponse(data=result)
    except Exception as exc:
        raise ServiceError(str(exc), code="PROVIDER_ERROR", http_status=502)
