"""Provider REST router."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from provider.registry import registry
from provider.schemas import ChatRequest, ProviderListResponse
from shared.errors import NotFoundError, ServiceError
from shared.model_cache import model_cache
from shared.models import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/providers", tags=["providers"])

_DEFAULT_MODEL = "claude-sonnet-4-20250514"


@router.get("", response_model=ProviderListResponse)
async def list_providers():
    return ProviderListResponse(data=registry.list())  # type: ignore[arg-type]


@router.get("/models")
async def list_models(
    provider: str | None = Query(None, description="Filter by provider name"),
):
    """List available models from configured providers (cached, TTL 5 min).

    Without ``?provider=``, returns models grouped by provider.  With the
    parameter, returns only the models for that specific provider.
    """
    result: dict[str, list[dict]] = {}

    provider_names = [provider] if provider else [p["name"] for p in registry.list()]

    for name in provider_names:
        cached = model_cache.get(name)
        if cached is not None:
            result[name] = cached
            continue

        p = registry.get(name)
        if p is None:
            continue

        try:
            models = await p.list_models()
        except Exception:
            logger.exception("list_models failed for provider '%s'", name)
            models = []

        model_cache.set(name, models)
        result[name] = models

    return ApiResponse(data=result)


@router.post("/models/refresh")
async def refresh_models(
    provider: str | None = Query(None, description="Refresh a single provider only"),
):
    """Force-refresh model caches from upstream APIs.

    Clears cached entries (all or for a specific provider) so the next
    ``GET /api/providers/models`` call re-fetches from the source.
    """
    cleared = model_cache.clear(provider)
    return ApiResponse(message=f"Cleared model cache for {cleared} provider(s)")


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
                provider.chat_completion_stream(  # type: ignore[arg-type]
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
