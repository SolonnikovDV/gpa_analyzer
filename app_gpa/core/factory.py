"""Application Factory — central module registry and lifecycle manager.

Usage in main.py / bootstrap.py:

    from core.factory import AppFactory
    from modules.agents import AgentModule
    from modules.analysis import AnalysisModule

    AppFactory.register("agents", AgentModule())
    AppFactory.register("analysis", AnalysisModule())
    AppFactory.wire()

Modules can be retrieved anywhere via:

    from core.factory import AppFactory
    agents = AppFactory.get("agents")
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class ModuleBase(Protocol):
    """Interface every plug-in module must satisfy."""

    name: str

    def setup(self) -> None:
        """Called once during AppFactory.wire(); initialise resources."""

    def health(self) -> Dict[str, Any]:
        """Return a health/status dict suitable for /health endpoints."""

    def metadata(self) -> Dict[str, Any]:
        """Return descriptive metadata: version, capabilities, config."""


class AppFactory:
    """Singleton registry that wires up all application modules.

    Modules are plain Python objects that implement ModuleBase.
    Registration is explicit (no magic auto-discovery) so that the
    dependency graph stays readable.
    """

    _modules: Dict[str, ModuleBase] = {}
    _wired: bool = False

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    @classmethod
    def register(cls, name: str, module: ModuleBase) -> None:
        """Register a module under *name*. Must be called before wire()."""
        if cls._wired:
            raise RuntimeError(
                f"AppFactory.wire() already called; cannot register '{name}' after startup."
            )
        cls._modules[name] = module

    @classmethod
    def get(cls, name: str) -> ModuleBase:
        """Retrieve a registered module by name. Raises KeyError if missing."""
        try:
            return cls._modules[name]
        except KeyError:
            registered = list(cls._modules.keys())
            raise KeyError(
                f"Module '{name}' not registered. Available: {registered}"
            ) from None

    @classmethod
    def has(cls, name: str) -> bool:
        return name in cls._modules

    @classmethod
    def all_modules(cls) -> Dict[str, ModuleBase]:
        return dict(cls._modules)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def wire(cls) -> None:
        """Call setup() on every registered module, in registration order."""
        if cls._wired:
            return
        for name, module in cls._modules.items():
            try:
                module.setup()
            except Exception as exc:
                raise RuntimeError(f"Module '{name}' failed during setup: {exc}") from exc
        cls._wired = True

    @classmethod
    def health_all(cls) -> Dict[str, Any]:
        """Aggregate health from all modules."""
        result: Dict[str, Any] = {}
        for name, module in cls._modules.items():
            try:
                result[name] = module.health()
            except Exception as exc:
                result[name] = {"ok": False, "error": str(exc)}
        return result

    @classmethod
    def reset(cls) -> None:
        """For testing: clear the registry."""
        cls._modules = {}
        cls._wired = False
