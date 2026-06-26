"""Plugin system — discover and load plugins from multiple sources.

Three discovery sources (mirroring Hermes Agent):
1. ``~/.hermes-engine/plugins/`` — user plugins
2. ``.hermes-engine/plugins/`` — project plugins
3. ``pip`` entry points — ``hermes_engine.plugins`` group
"""

from __future__ import annotations

import importlib
import logging
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import importlib.metadata as metadata
else:
    import importlib_metadata as metadata  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "hermes_engine.plugins"


class Plugin(ABC):
    """Base class for all Hermes Engine plugins."""

    name: str = "base"
    version: str = "0.1.0"

    @abstractmethod
    def activate(self, app: Any) -> None:
        """Called when the plugin is loaded."""
        ...

    def deactivate(self) -> None:
        """Called when the plugin is unloaded (optional)."""
        pass


class PluginLoader:
    """Discovers and loads plugins from filesystem and entry points."""

    def __init__(self, extra_dirs: list[str] | None = None) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._extra_dirs = extra_dirs or []

    def discover(self) -> list[str]:
        """Discover available plugin names (does not load them)."""
        names: list[str] = []

        # 1. User plugins
        user_dir = Path.home() / ".hermes-engine" / "plugins"
        if user_dir.is_dir():
            for p in user_dir.iterdir():
                if p.is_dir() and (p / "__init__.py").exists():
                    names.append(f"user:{p.name}")

        # 2. Project plugins
        project_dir = Path.cwd() / ".hermes-engine" / "plugins"
        if project_dir.is_dir():
            for p in project_dir.iterdir():
                if p.is_dir() and (p / "__init__.py").exists():
                    names.append(f"project:{p.name}")

        # 3. Extra dirs from settings
        for d in self._extra_dirs:
            dpath = Path(d)
            if dpath.is_dir():
                for p in dpath.iterdir():
                    if p.is_dir() and (p / "__init__.py").exists():
                        names.append(f"extra:{p.name}")

        # 4. Pip entry points
        try:
            for ep in metadata.entry_points(group=ENTRY_POINT_GROUP):
                names.append(f"pip:{ep.name}")
        except Exception:
            logger.debug("No entry points found for group '%s'", ENTRY_POINT_GROUP)

        return sorted(set(names))

    def load(self, name: str) -> Plugin | None:
        """Load a plugin by name (e.g. 'user:myplugin', 'pip:myplugin')."""
        if name in self._plugins:
            return self._plugins[name]

        prefix, plugin_name = name.split(":", 1) if ":" in name else ("user", name)

        if prefix == "pip":
            try:
                eps = metadata.entry_points(group=ENTRY_POINT_GROUP)
                for ep in eps:
                    if ep.name == plugin_name:
                        plugin_cls = ep.load()
                        instance = plugin_cls()
                        instance.name = plugin_name
                        self._plugins[name] = instance
                        logger.info("Plugin loaded: %s (pip)", name)
                        return instance  # type: ignore[no-any-return]
            except Exception as exc:
                logger.warning("Failed to load pip plugin '%s': %s", name, exc)
                return None

        # Filesystem plugin
        dir_map = {
            "user": Path.home() / ".hermes-engine" / "plugins" / plugin_name,
            "project": Path.cwd() / ".hermes-engine" / "plugins" / plugin_name,
        }
        for d in self._extra_dirs:
            dir_map[f"extra:{Path(d).name}"] = Path(d) / plugin_name

        for pfx, pdir in dir_map.items():
            if prefix == pfx or (prefix == "extra" and pfx.startswith("extra")):
                if pdir.is_dir() and (pdir / "__init__.py").exists():
                    try:
                        sys.path.insert(0, str(pdir.parent))
                        mod = importlib.import_module(plugin_name)
                        for attr in dir(mod):
                            obj = getattr(mod, attr)
                            if (
                                isinstance(obj, type)
                                and issubclass(obj, Plugin)
                                and obj is not Plugin
                            ):
                                instance = obj()
                                instance.name = plugin_name
                                self._plugins[name] = instance
                                logger.info("Plugin loaded: %s (%s)", name, pfx)
                                return instance
                    except Exception as exc:
                        logger.warning("Failed to load plugin '%s': %s", name, exc)
                        return None

        logger.warning("Plugin '%s' not found", name)
        return None

    def list_loaded(self) -> list[str]:
        """Return names of currently loaded plugins."""
        return list(self._plugins.keys())

    def unload_all(self) -> None:
        """Deactivate and unload all plugins."""
        for instance in self._plugins.values():
            try:
                instance.deactivate()
            except Exception:
                logger.debug("Plugin deactivation failed", exc_info=True)
        self._plugins.clear()
