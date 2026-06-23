"""Provider REST router."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi import Request
from fastapi.responses import StreamingResponse

from provider.registry import registry
from provider.schemas import ChatRequest, ProviderListResponse
from shared.errors import NotFoundError, ServiceError

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("", response_model=ProviderListResponse)
async def list_providers():
    return ProviderListResponse(data=registry.list())


@router.post("/chat")
async def chat(request: ChatRequest, http_request: Request):
    """Send a chat completion request to the specified provider."""
    provider = registry.get(request.provider)
    if not provider:
        raise NotFoundError(f"Provider '{request.provider}' not found")

    try:
        if request.stream:
            return StreamingResponse(
                provider.chat_completion_stream(
                    messages=[m.model_dump() if hasattr(m, 'model_dump') else m for m in request.messages],
                    model=request.model or "claude-sonnet-4-20250514",
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    tools=request.tools,
                ),
                media_type="text/event-stream",
            )
        else:
            result = await provider.chat_completion(
                messages=[m.model_dump() if hasattr(m, 'model_dump') else m for m in request.messages],
                model=request.model or "claude-sonnet-4-20250514",
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                tools=request.tools,
            )
            return {"success": True, "data": result}
    except Exception as exc:
        raise ServiceError(str(exc), code="PROVIDER_ERROR", http_status=502)
