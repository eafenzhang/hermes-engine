"""Gateway — messaging platform webhook adapters.

Each adapter translates platform-specific webhook payloads into agent
turns and formats the response for the platform.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class GatewayAdapter(ABC):
    """Abstract webhook-to-agent adapter."""

    platform: str = "base"

    @abstractmethod
    async def handle_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Process a webhook payload and return a response."""
        ...

    @abstractmethod
    async def send_message(self, recipient: str, text: str) -> bool:
        """Send a message to a platform recipient."""
        ...


class WebhookAdapter(GatewayAdapter):
    """Generic webhook adapter — parses JSON payload, runs agent, returns text."""

    platform = "webhook"

    def __init__(self) -> None:
        self._message_handler: Any = None  # set by register_handler

    def register_handler(self, handler: Any) -> None:
        self._message_handler = handler

    async def handle_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = payload.get("message") or payload.get("text") or ""
        if not message and "messages" in payload:
            msg_list = payload["messages"]
            last = msg_list[-1] if isinstance(msg_list, list) else msg_list
            message = last.get("content", "") if isinstance(last, dict) else str(last)
        return {"message": message, "response": None}  # caller runs agent

    async def send_message(self, recipient: str, text: str) -> bool:
        logger.info("Webhook → %s: %s", recipient, text[:100])
        return True
