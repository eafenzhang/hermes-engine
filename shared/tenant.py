"""Tenant middleware — extract tenant identity from headers."""

from __future__ import annotations

import logging

from fastapi import Request

logger = logging.getLogger(__name__)

_TENANT_HEADER = "X-Tenant-ID"
_DEFAULT_TENANT = "default"


def get_tenant_id(request: Request) -> str:
    """Extract tenant ID from request state (set by middleware)."""
    return getattr(request.state, "tenant_id", _DEFAULT_TENANT)


class TenantMiddleware:
    """ASGI middleware: extract X-Tenant-ID and attach to request state."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            tid = headers.get(b"x-tenant-id", b"default").decode("utf-8", errors="replace")
            scope["state"] = scope.get("state", {})
            scope["state"]["tenant_id"] = tid or _DEFAULT_TENANT
        await self.app(scope, receive, send)
