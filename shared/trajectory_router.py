"""Trajectory REST router — conversation export endpoints."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from fastapi import APIRouter

from shared.models import ApiResponse
from shared.trajectory import export_sharegpt


class TrajectoryExportRequest(BaseModel):
    messages: list[dict] = Field(..., min_length=1)
    output_path: str = "trajectory.json"


router = APIRouter(prefix="/api/trajectories", tags=["trajectories"])


@router.post("/export")
async def export_trajectory(body: TrajectoryExportRequest):
    """Export a conversation as ShareGPT JSON."""
    output_path = Path(body.output_path)
    result = export_sharegpt(body.messages, output_path)
    return ApiResponse(data=result, message="Trajectory exported")
