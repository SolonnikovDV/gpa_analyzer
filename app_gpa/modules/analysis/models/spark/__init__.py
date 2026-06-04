"""Spark stack analyzer executor."""
from __future__ import annotations

from typing import Any, Dict


class SparkAnalyzer:
    """Executor for Apache Spark SQL / DataFrame analysis."""

    stack = "spark"

    def analyze(self, source_text: str, **kwargs: Any) -> Dict[str, Any]:
        from modules.analysis.runtime_analyzers import analyze_spark

        return analyze_spark(source_text, **kwargs)

    def discover(self, source_text: str, **kwargs: Any) -> Dict[str, Any]:
        from modules.analysis.runtime_analyzers import discover_spark

        return discover_spark(source_text, **kwargs)

    def lint(self, source_text: str, **kwargs: Any) -> Dict[str, Any]:
        from modules.analysis.lint.factory import get_linter

        return get_linter("spark").validate(source_text, **kwargs)
