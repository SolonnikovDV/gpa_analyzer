"""PySpark stack analyzer executor."""
from __future__ import annotations

from typing import Any, Dict


class PySparkAnalyzer:
    """Executor for PySpark script analysis."""

    stack = "pyspark"

    def analyze(self, source_text: str, **kwargs: Any) -> Dict[str, Any]:
        from modules.analysis.runtime_analyzers import analyze_pyspark

        return analyze_pyspark(source_text, **kwargs)

    def discover(self, source_text: str, **kwargs: Any) -> Dict[str, Any]:
        from modules.analysis.runtime_analyzers import discover_pyspark

        return discover_pyspark(source_text, **kwargs)

    def lint(self, source_text: str, **kwargs: Any) -> Dict[str, Any]:
        from modules.analysis.lint.factory import get_linter

        return get_linter("pyspark").validate(source_text, **kwargs)
