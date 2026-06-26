"""Trajectory export — ShareGPT format for training data generation.

Exports conversation turns as ShareGPT-compatible JSONL for downstream
fine-tuning of agent models.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def export_sharegpt(messages: list[dict[str, Any]], output_path: Path) -> dict[str, Any]:
    """Export a message list in ShareGPT format.

    Returns a descriptor dict with output path and message count.
    """
    # ShareGPT format: list of {"from": "human"|"gpt", "value": "..."}
    conversations: list[dict[str, str]] = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                b.get("text", "") for b in content if isinstance(b, dict)
            )
        if role == "user":
            conversations.append({"from": "human", "value": str(content)})
        elif role == "assistant":
            conversations.append({"from": "gpt", "value": str(content)})
        elif role == "system":
            conversations.append({"from": "system", "value": str(content)})

    record = {
        "id": f"hermes-trajectory-{int(time.time())}",
        "conversations": conversations,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("Exported %d-turn trajectory to %s", len(conversations), output_path)
    return {"path": str(output_path), "turns": len(conversations), "format": "sharegpt"}


def export_sharegpt_batch(
    conversations: list[list[dict[str, Any]]],
    output_path: Path,
) -> dict[str, Any]:
    """Export multiple conversations as a ShareGPT JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_turns = 0
    with output_path.open("w", encoding="utf-8") as f:
        for i, msgs in enumerate(conversations):
            turns: list[dict[str, str]] = []
            for m in msgs:
                role = m.get("role", "")
                content = m.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict)
                    )
                if role == "user":
                    turns.append({"from": "human", "value": str(content)})
                elif role == "assistant":
                    turns.append({"from": "gpt", "value": str(content)})
                elif role == "system":
                    turns.append({"from": "system", "value": str(content)})

            record = {"id": f"hermes-trajectory-{i}-{int(time.time())}", "conversations": turns}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            total_turns += len(turns)

    logger.info(
        "Exported %d conversations (%d turns) to %s",
        len(conversations), total_turns, output_path,
    )
    return {
        "path": str(output_path),
        "conversations": len(conversations),
        "turns": total_turns,
        "format": "sharegpt-jsonl",
    }
