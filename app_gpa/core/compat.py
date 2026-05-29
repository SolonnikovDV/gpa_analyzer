"""Legacy import aliases: agent.* → modules.agents.*, detailed.* → modules.analysis.*."""
from __future__ import annotations

import importlib.abc
import importlib.util
import sys
from types import ModuleType
from typing import Optional, Sequence, Tuple

_PREFIX_MAP: Sequence[Tuple[str, str]] = (
    ("agent", "modules.agents"),
    ("detailed", "modules.analysis"),
)


def _map_name(fullname: str) -> Optional[str]:
    for legacy, modern in _PREFIX_MAP:
        if fullname == legacy or fullname.startswith(f"{legacy}."):
            return modern + fullname[len(legacy) :]
    return None


class _LegacyLoader(importlib.abc.Loader):
    def __init__(self, fullname: str, target_name: str) -> None:
        self.fullname = fullname
        self.target_name = target_name

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> Optional[ModuleType]:
        return None

    def exec_module(self, module: ModuleType) -> None:
        loaded = importlib.import_module(self.target_name)
        module.__dict__.update(loaded.__dict__)
        module.__loader__ = self
        module.__name__ = self.fullname
        module.__package__ = self.fullname.rpartition(".")[0] if "." in self.fullname else self.fullname
        if hasattr(loaded, "__path__"):
            module.__path__ = loaded.__path__  # type: ignore[attr-defined]
        module.__spec__ = importlib.util.spec_from_loader(self.fullname, self)
        sys.modules[self.fullname] = module


class _LegacyPackageFinder:
    """Meta path finder that redirects legacy top-level packages to modules/."""

    def find_spec(self, fullname: str, path: Optional[list] = None, target: Optional[ModuleType] = None):
        mapped = _map_name(fullname)
        if mapped is None:
            return None
        loader = _LegacyLoader(fullname, mapped)
        return importlib.util.spec_from_loader(fullname, loader, is_package=mapped.endswith("__init__") or _is_package(mapped))


def _is_package(name: str) -> bool:
    spec = importlib.util.find_spec(name)
    return bool(spec and spec.submodule_search_locations)


def install_compat_imports() -> None:
    if any(isinstance(finder, _LegacyPackageFinder) for finder in sys.meta_path):
        return
    sys.meta_path.insert(0, _LegacyPackageFinder())
