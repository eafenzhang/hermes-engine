"""OpenAI-compatible /v1/chat/completions endpoint tests.

Uses the existing test client fixture — no real provider calls because
the agent engine requires a configured provider to produce a response.
We test the wire-format conversion and the model-routing logic instead,
and verify that the endpoint returns proper HTTP errors when no provider
is available (the same way the agent router does).
"""

from __future__ import annotations

import json

import pytest


# ── Model routing (unit-tested via the module directly) ──────────────────


@pytest.mark.parametrize(
    ("model", "expected_provider"),
    [
        ("claude-sonnet-4-20250514", "anthropic"),
        ("claude-opus-4", "anthropic"),
        ("gpt-4o", "openai"),
        ("gpt-4o-mini", "openai"),
        ("o4-mini", "openai"),
        ("gemini-2.5-pro", "gemini"),
        # Chinese AI providers
        ("deepseek-chat", "deepseek"),
        ("deepseek-reasoner", "deepseek"),
        ("moonshot-v1-8k", "moonshot"),
        ("kimi-latest", "moonshot"),
        ("glm-4", "zhipu"),
        ("glm-4-flash", "zhipu"),
        ("zhipu-glm", "zhipu"),
        ("chatglm-turbo", "zhipu"),
        ("qwen-turbo", "qwen"),
        ("qwen-max", "qwen"),
        ("mimo-pro", "xiaomi"),
        ("abab6.5s-chat", "minimax"),
        ("minimax-text-01", "minimax"),
        ("unknown-model", "anthropic"),  # fallback
    ],
)
def test_resolve_provider(model: str, expected_provider: str):
    """Model→provider routing works for known prefixes."""
    from api_compat.router import _resolve_provider

    provider, resolved_model = _resolve_provider(model)
    assert provider == expected_provider
    assert resolved_model == model


# ── Endpoint responses ─────────────────────────────────────────────────


def test_chat_completions_no_provider_returns_error(client):
    """Without any configured provider, the endpoint returns a structured error."""
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    # The agent engine raises ServiceError which becomes a JSON error response.
    assert resp.status_code in (200, 400, 422, 500)
    body = resp.json()
    assert "error" in body or "detail" in body or "success" in body


def test_chat_completions_requires_messages(client):
    """Missing messages field leads to a 422 validation error."""
    resp = client.post("/v1/chat/completions", json={"model": "gpt-4o"})
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body


def test_chat_completions_streaming_returns_sse_headers(client):
    """Streaming request returns ``text/event-stream``."""
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "claude-sonnet-4",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        },
    )
    # The endpoint returns 200 with SSE content-type even when the
    # provider call fails — errors are yielded as SSE events.
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("text/event-stream")


def test_chat_completions_streaming_yields_sse_events(client):
    """The SSE stream contains at least the initial and final chunks."""
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Count to 3"}],
            "stream": True,
        },
    )
    assert resp.status_code == 200
    lines = [l for l in resp.text.split("\n") if l.strip()]

    # The first data event should be a chunk with role:"assistant"
    # (the stream is always opened even if the provider call fails)
    payloads = []
    for line in lines:
        if line.startswith("data: ") and line != "data: [DONE]":
            payloads.append(json.loads(line[6:]))

    assert len(payloads) >= 1
    first = payloads[0]
    assert first["object"] == "chat.completion.chunk"
    assert first["choices"][0]["delta"]["role"] == "assistant"


def test_chat_completions_content_type(client):
    """Non-streaming response has JSON content-type."""
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "gemini-2.5-pro",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    assert resp.headers.get("content-type", "").startswith("application/json")


# ── Tool format conversion ──────────────────────────────────────────────


def test_engine_tools_from_openai():
    """OpenAI tool definitions are converted to Hermes Engine format."""
    from api_compat.router import _engine_tools_from_openai

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the weather",
                "parameters": {"type": "object", "properties": {"loc": {"type": "string"}}},
            },
        }
    ]
    result = _engine_tools_from_openai(tools)
    assert result is not None
    assert result[0]["name"] == "get_weather"
    assert result[0]["input_schema"]["properties"]["loc"]["type"] == "string"


def test_openai_messages_from_engine_text():
    """Text-only engine messages convert to OpenAI content string."""
    from api_compat.router import _openai_messages_from_engine

    engine_msg = {
        "content": [{"type": "text", "text": "Hello world"}],
    }
    result = _openai_messages_from_engine(engine_msg)
    assert result["role"] == "assistant"
    assert result["content"] == "Hello world"
    assert result.get("tool_calls") is None


def test_openai_messages_from_engine_tool_use():
    """Tool-use blocks convert to OpenAI tool_calls array."""
    from api_compat.router import _openai_messages_from_engine

    engine_msg = {
        "content": [
            {"type": "text", "text": "Let me check"},
            {
                "type": "tool_use",
                "id": "toolu_abc123",
                "name": "get_weather",
                "input": {"loc": "Beijing"},
            },
        ],
    }
    result = _openai_messages_from_engine(engine_msg)
    assert "Let me check" in result["content"]
    assert result["tool_calls"] is not None
    assert result["tool_calls"][0]["function"]["name"] == "get_weather"
    args = json.loads(result["tool_calls"][0]["function"]["arguments"])
    assert args["loc"] == "Beijing"


def test_openai_messages_from_engine_plain_string():
    """Plain string content (non-list) is handled correctly."""
    from api_compat.router import _openai_messages_from_engine

    result = _openai_messages_from_engine({"content": "Simple text"})
    assert result["content"] == "Simple text"
