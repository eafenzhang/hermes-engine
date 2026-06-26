"""Browser tools — web_fetch and web_search for agent web interaction."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

WEB_FETCH_SCHEMA = {
    "description": "Fetch a web page and convert it to markdown text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 15)"},
        },
        "required": ["url"],
    },
}

WEB_SEARCH_SCHEMA = {
    "description": "Search the web and return result titles and URLs.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Max results (default 5)"},
        },
        "required": ["query"],
    },
}

_HTML_STRIP_RE = re.compile(r"<[^>]+>")


async def web_fetch(url: str, timeout: int = 15) -> str:
    """Fetch a URL and return plain-text content."""
    try:
        import httpx
    except ImportError:
        return "Error: httpx not installed. Install with: pip install httpx"

    try:
        async with httpx.AsyncClient(timeout=float(timeout)) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()

        text = resp.text
        # Basic HTML → text
        text = _HTML_STRIP_RE.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
        # Truncate
        if len(text) > 8000:
            text = text[:8000] + "..."
        return text or "(empty page)"
    except Exception as exc:
        return f"Error fetching {url}: {exc}"


async def web_search(query: str, max_results: int = 5) -> str:
    """Perform a web search and return formatted results.

    Uses DuckDuckGo HTML search (no API key required).
    """
    try:
        import httpx
    except ImportError:
        return "Error: httpx not installed."

    try:
        search_url = f"https://html.duckduckgo.com/html/?q={query}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                search_url,
                headers={"User-Agent": "Hermes-Engine/1.0"},
                follow_redirects=True,
            )
            resp.raise_for_status()

        html = resp.text
        # Extract result snippets
        results: list[str] = []
        snippet_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        for m in snippet_pattern.finditer(html):
            url = m.group(1)
            title = _HTML_STRIP_RE.sub("", m.group(2)).strip()
            snippet = _HTML_STRIP_RE.sub("", m.group(3)).strip()
            results.append(f"- **{title}**\n  {url}\n  {snippet}")

        if not results:
            # Fallback: simple link extraction
            link_pattern = re.compile(r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
            for m in link_pattern.finditer(html):
                url = m.group(1)
                title = _HTML_STRIP_RE.sub("", m.group(2)).strip()
                if title and url.startswith("http"):
                    results.append(f"- **{title}**\n  {url}")

        results = results[:max_results]
        return "\n\n".join(results) if results else f"No results found for '{query}'"
    except Exception as exc:
        return f"Error searching for '{query}': {exc}"
