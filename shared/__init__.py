"""Shared infrastructure — models, errors, events, database utilities."""

from shared.models import ApiResponse, ErrorResponse, PaginatedResponse, HealthResponse
from shared.errors import ServiceError, NotFoundError, ValidationError
from shared.event import EventBus, DomainEvent, bus

__all__ = [
    "ApiResponse", "ErrorResponse", "PaginatedResponse", "HealthResponse",
    "ServiceError", "NotFoundError", "ValidationError",
    "EventBus", "DomainEvent", "bus",
]
