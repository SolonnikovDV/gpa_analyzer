"""Analysis module public API.

Usage:
    from modules.analysis import AnalysisModule
    module = AnalysisModule()
    module.setup()

The module is registered with AppFactory in core/bootstrap.py.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class AnalysisModule:
    """Plug-in module for Greenplum/Spark/PySpark analysis.

    Stack-specific executors live under models/.
    Shared infra (jobs, persistence, lint, runtime registry) stays
    in the flat package and is accessed via this public interface.
    """

    name = "analysis"

    # ------------------------------------------------------------------
    # ModuleBase implementation
    # ------------------------------------------------------------------

    def setup(self) -> None:
        from core.paths import ensure_runtime_dirs
        from core.settings import settings
        from modules.analysis.persistence_service import PersistenceService

        ensure_runtime_dirs()
        # Warm up persistence (creates SQLite tables on first run)
        PersistenceService(settings.runtime_store_dir, settings.persistence_db_path)

    def health(self) -> Dict[str, Any]:
        from modules.analysis.observability import check_sqlite_health
        from core.settings import settings

        db_ok = check_sqlite_health(settings.persistence_db_path)
        return {"ok": db_ok, "sqlite": db_ok}

    def metadata(self) -> Dict[str, Any]:
        from modules.analysis.runtime_registry import get_supported_stacks, get_supported_scenarios

        return {
            "name": self.name,
            "stacks": get_supported_stacks(),
            "scenarios": get_supported_scenarios(),
        }

    # ------------------------------------------------------------------
    # Public API — used by services/ and web routes
    # ------------------------------------------------------------------

    def get_analyzer(self, stack: str = "greenplum"):
        """Return the stack-appropriate analyzer executor."""
        from modules.analysis.models import get_analyzer

        return get_analyzer(stack)

    def get_job_service(
        self,
        *,
        runtime_store_dir: Optional[str] = None,
        persistence_db_path: Optional[str] = None,
    ):
        from core.settings import settings
        from modules.analysis.persistence_service import PersistenceService

        p = PersistenceService(
            runtime_store_dir or settings.runtime_store_dir,
            persistence_db_path or settings.persistence_db_path,
        )
        return p.job_store

    def lint(self, *, stack: str, source_text: str, **kwargs: Any) -> Dict[str, Any]:
        from modules.analysis.lint.factory import get_linter

        linter = get_linter(stack)
        return linter.validate(source_text, **kwargs)

    def runtime_descriptor(self, stack: str, scenario: Optional[str] = None) -> Dict[str, Any]:
        from modules.analysis.runtime_registry import (
            get_runtime_descriptor,
            get_supported_scenarios,
            get_supported_stacks,
            normalize_scenario,
            normalize_stack,
        )

        s = normalize_stack(stack)
        sc = normalize_scenario(scenario)
        d = get_runtime_descriptor(s, sc)
        return {
            "stack": d.stack,
            "scenario": d.scenario,
            "descriptor": d.to_dict(),
            "supported_stacks": get_supported_stacks(),
            "supported_scenarios": get_supported_scenarios(),
        }
