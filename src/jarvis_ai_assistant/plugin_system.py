"""Plugin discovery and command routing for optional Jarvis skills."""

from __future__ import annotations

from importlib import import_module
import logging
import pkgutil
from typing import TYPE_CHECKING, Protocol

from .models import AssistantResponse

if TYPE_CHECKING:
    from .assistant import JarvisAssistant

LOGGER = logging.getLogger(__name__)


class SkillPlugin(Protocol):
    """Protocol every skill plugin must implement."""

    name: str

    def handle(self, command: str, *, assistant: JarvisAssistant) -> AssistantResponse | None:
        """Return a response when handled, else None to continue normal routing."""


class PluginManager:
    """Discovers and dispatches command plugins from the plugins package."""

    def __init__(self) -> None:
        self._plugins: list[SkillPlugin] = []
        self._load_plugins()

    @property
    def plugins(self) -> list[SkillPlugin]:
        return self._plugins

    def handle_command(self, command: str, *, assistant: JarvisAssistant) -> AssistantResponse | None:
        """Try all plugins and return the first non-empty response."""
        normalized = command.strip()
        if not normalized:
            return None

        for plugin in self._plugins:
            response = plugin.handle(normalized, assistant=assistant)
            if response is not None:
                return response
        return None

    def _load_plugins(self) -> None:
        from . import plugins as plugins_package

        discovered: list[SkillPlugin] = []
        for module_info in pkgutil.iter_modules(plugins_package.__path__):
            if module_info.name.startswith("_"):
                continue
            module = import_module(f"{plugins_package.__name__}.{module_info.name}")
            register = getattr(module, "register", None)
            if register is None:
                LOGGER.warning("Plugin module %s has no register() function.", module_info.name)
                continue

            plugin = register()
            if not hasattr(plugin, "handle") or not hasattr(plugin, "name"):
                LOGGER.warning("Plugin module %s returned an invalid plugin object.", module_info.name)
                continue
            discovered.append(plugin)

        self._plugins = discovered
