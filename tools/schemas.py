"""Tools schemas / DTOs."""

from __future__ import annotations

from pydantic import BaseModel


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict = {}


class ToolExecuteRequest(BaseModel):
    calls: list[ToolCallRequest]
    concurrent: bool = False


class ToolInfo(BaseModel):
    name: str
    description: str
    input_schema: dict = {}
