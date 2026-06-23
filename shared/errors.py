"""Unified error handling — ServiceError → HTTPException → ErrorResponse."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse

from shared.models import ErrorResponse


class ServiceError(Exception):
    """Base domain error raised by service layers."""

    def __init__(
        self,
        message: str,
        code: str = "SERVICE_ERROR",
        details: dict[str, Any] | None = None,
        http_status: int = 400,
    ) -> None:
        self.message = message
        self.code = code
        self.details = details
        self.http_status = http_status
        super().__init__(message)


class NotFoundError(ServiceError):
    def __init__(
        self,
        message: str = "Resource not found",
        code: str = "NOT_FOUND",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details, http_status=404)


class ValidationError(ServiceError):
    def __init__(
        self,
        message: str = "Validation failed",
        code: str = "VALIDATION_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details, http_status=422)


async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    """Convert ServiceError → ErrorResponse JSON."""
    return JSONResponse(
        status_code=exc.http_status,
        content=ErrorResponse(
            error=exc.message,
            code=exc.code,
            details=exc.details,
        ).model_dump(),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Convert unhandled HTTPException → ErrorResponse JSON."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=str(exc.detail),
            code="HTTP_ERROR",
        ).model_dump(),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort catch-all for unhandled exceptions."""
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            code="INTERNAL_ERROR",
        ).model_dump(),
    )
