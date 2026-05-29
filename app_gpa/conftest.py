"""Pytest bootstrap: legacy import aliases and env loading."""
from __future__ import annotations

from core.compat import install_compat_imports

install_compat_imports()

from core.settings import load_project_environment  # noqa: E402

load_project_environment()
