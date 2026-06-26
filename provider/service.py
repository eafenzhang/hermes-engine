"""Provider service — register, list, and dispatch chat requests."""

from __future__ import annotations

import importlib
import logging

from provider.registry import registry
from config.settings import Settings

logger = logging.getLogger(__name__)

# ── Provider descriptors ─────────────────────────────────────────────────
# Each entry is (settings_attr_prefix, registry_name).
# "registry_name" is the string key used in ProviderRegistry and
# api_compat model routing.
#
# Dedicated providers have their own adapter class (Anthropic, Gemini);
# OpenAI-compatible providers reuse OpenAIAdapter with a custom base_url.

_DEDICATED_PROVIDERS: list[tuple[str, str, str]] = [
    # (attr_prefix, registry_name, adapter_module_path)
    ("anthropic", "anthropic", "provider.anthropic_adapter"),
    ("gemini", "gemini", "provider.gemini_adapter"),
]

_ANTHROPIC_COMPAT_PROVIDERS: list[tuple[str, str]] = [
    # (attr_prefix, registry_name)
    # Anthropic‑compatible proxy / gateway providers that reuse AnthropicAdapter
    # with a custom base_url and connectivity model.
    ("anthropic_compat", "anthropic_compat"),
]

_OPENAI_COMPAT_PROVIDERS: list[tuple[str, str]] = [
    # (attr_prefix, registry_name)
    ("openai", "openai"),
    ("deepseek", "deepseek"),
    ("moonshot", "moonshot"),
    ("zhipu", "zhipu"),
    ("qwen", "qwen"),
    ("xiaomi", "xiaomi"),
    ("minimax", "minimax"),
]


def _camel_case(s: str) -> str:
    """Convert a snake_case prefix to CamelCase, e.g. 'anthropic' → 'Anthropic'."""
    return "".join(part.capitalize() for part in s.split("_"))


def _register_dedicated_provider(prefix: str, name: str, module_path: str, api_key: str, base_url: str | None = None) -> None:
    """Import a dedicated adapter class, instantiate (with optional base_url), and register it."""
    mod = importlib.import_module(module_path)
    class_name = f"{_camel_case(prefix)}Adapter"
    adapter_cls = getattr(mod, class_name)
    registry.register(adapter_cls(api_key=api_key, base_url=base_url))


def _register_anthropic_compat_provider(prefix: str, name: str, settings: Settings) -> None:
    """Import AnthropicAdapter, instantiate with custom name/base_url/model, and register."""
    from provider.anthropic_adapter import AnthropicAdapter

    api_key: str = getattr(settings, f"{prefix}_api_key", "")
    base_url_field = f"{prefix}_base_url"
    raw_base_url: str = getattr(settings, base_url_field, "") or ""
    model_field = f"{prefix}_model"
    connectivity_model: str = getattr(settings, model_field, "claude-sonnet-4-20250514")

    adapter = AnthropicAdapter(
        api_key=api_key,
        base_url=raw_base_url or None,
    )
    adapter.name = name
    adapter._connectivity_model = connectivity_model
    registry.register(adapter)


def _register_openai_compat_provider(prefix: str, name: str, settings: Settings) -> None:
    """Import OpenAIAdapter, instantiate with custom name and base_url, and register."""
    from provider.openai_adapter import OpenAIAdapter

    api_key: str = getattr(settings, f"{prefix}_api_key", "")
    base_url_field = f"{prefix}_base_url"
    raw_base_url: str = getattr(settings, base_url_field, "") or ""

    # Xiaomi has no default base_url — skip registration when the URL is
    # not configured (otherwise we'd connect to OpenAI's endpoint by mistake).
    if not raw_base_url and prefix == "xiaomi":
        logger.info(
            "Xiaomi Mimo provider skipped — set HERMES_XIAOMI_BASE_URL and "
            "HERMES_XIAOMI_API_KEY to enable"
        )
        return

    adapter = OpenAIAdapter(
        api_key=api_key,
        base_url=raw_base_url or None,
    )
    adapter.name = name
    registry.register(adapter)


def init_providers(settings: Settings) -> None:
    """Register all configured providers at startup (lazy imports)."""

    # ── Dedicated providers (Anthropic, Gemini) ──────────────────────────
    for prefix, name, module_path in _DEDICATED_PROVIDERS:
        api_key: str = getattr(settings, f"{prefix}_api_key", "")
        if not api_key:
            continue
        try:
            base_url_field = f"{prefix}_base_url"
            raw_base_url: str = getattr(settings, base_url_field, "") or ""
            _register_dedicated_provider(
                prefix, name, module_path, api_key,
                base_url=raw_base_url or None,
            )
        except ImportError:
            logger.warning("%s SDK not installed; skipping %s provider", prefix, name)
        except Exception as exc:
            logger.warning("Failed to register %s provider: %s", name, exc)

    # ── Anthropic‑compatible providers (proxy / gateway) ────────────────
    for prefix, name in _ANTHROPIC_COMPAT_PROVIDERS:
        compat_key: str = getattr(settings, f"{prefix}_api_key", "")
        if not compat_key:
            continue
        compat_base_field = f"{prefix}_base_url"
        anthropic_base_url: str = getattr(settings, compat_base_field, "") or ""
        if not anthropic_base_url:
            logger.info(
                "Anthropic‑compat provider '%s' skipped — set HERMES_%s_BASE_URL",
                name, prefix.upper(),
            )
            continue
        try:
            _register_anthropic_compat_provider(prefix, name, settings)
        except ImportError:
            logger.warning("anthropic SDK not installed; skipping %s provider", name)
        except Exception as exc:
            logger.warning("Failed to register %s provider: %s", name, exc)

    # ── OpenAI-compatible providers ─────────────────────────────────────
    for prefix, name in _OPENAI_COMPAT_PROVIDERS:
        openai_key: str = getattr(settings, f"{prefix}_api_key", "")
        if not openai_key:
            continue
        try:
            _register_openai_compat_provider(prefix, name, settings)
        except ImportError:
            logger.warning("openai SDK not installed; skipping %s provider", name)
        except Exception as exc:
            logger.warning("Failed to register %s provider: %s", name, exc)
