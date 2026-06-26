"""Tools schemas / DTOs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel):
    name: str = Field(..., min_length=1)
    arguments: dict = Field(default_factory=dict)


class ToolExecuteRequest(BaseModel):
    calls: list[ToolCallRequest] = Field(..., min_length=1)
    concurrent: bool = False


class ToolInfo(BaseModel):
    name: str
    description: str
    input_schema: dict = Field(default_factory=dict)
