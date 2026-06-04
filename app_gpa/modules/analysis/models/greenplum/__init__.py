"""GreenPlum stack analyzer executor."""
from __future__ import annotations

from typing import Any, Dict, Optional


class GreenplumAnalyzer:
    """Executor for GreenPlum/PostgreSQL PL/pgSQL analysis.

    Delegates heavy lifting to DetailedGreenplumFunctionAnalyzer and
    AnalysisOrchestrator; exposes a clean protocol surface.
    """

    stack = "greenplum"

    def analyze(self, source_text: str, **kwargs: Any) -> Dict[str, Any]:
        from modules.analysis.detailed_analyzer import DetailedGreenplumFunctionAnalyzer

        analyzer = DetailedGreenplumFunctionAnalyzer(source_text, **_greenplum_kwargs(kwargs))
        return analyzer.analyze()

    def discover(self, source_text: str, **kwargs: Any) -> Dict[str, Any]:
        from modules.analysis.detailed_analyzer import DetailedGreenplumFunctionAnalyzer

        analyzer = DetailedGreenplumFunctionAnalyzer(source_text, **_greenplum_kwargs(kwargs))
        return analyzer.discover()

    def lint(self, source_text: str, **kwargs: Any) -> Dict[str, Any]:
        from modules.analysis.lint.factory import get_linter

        return get_linter("greenplum").validate(source_text, **kwargs)


def _greenplum_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {
        "conn_string", "segments", "ram_per_seg_gb",
        "analysis_mode", "loader_mode", "use_agent",
    }
    return {k: v for k, v in kwargs.items() if k in allowed}
