"""Stack-specific analyzer executors.

Add a new stack:
  1. Create modules/analysis/models/<stack>/__init__.py
  2. Implement StackAnalyzer Protocol
  3. Register in _ANALYZERS below — no other files change.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class StackAnalyzer(Protocol):
    """Interface every stack-specific analyzer must satisfy."""

    stack: str

    def analyze(self, source_text: str, **kwargs) -> dict: ...

    def discover(self, source_text: str, **kwargs) -> dict: ...


def get_analyzer(stack: str) -> StackAnalyzer:
    """Return the analyzer for the given stack name."""
    from modules.analysis.runtime_registry import normalize_stack

    s = normalize_stack(stack)
    from modules.analysis.models.greenplum import GreenplumAnalyzer
    from modules.analysis.models.spark import SparkAnalyzer
    from modules.analysis.models.pyspark import PySparkAnalyzer

    _ANALYZERS = {
        "greenplum": GreenplumAnalyzer,
        "spark": SparkAnalyzer,
        "pyspark": PySparkAnalyzer,
    }
    cls = _ANALYZERS.get(s)
    if cls is None:
        raise ValueError(f"No analyzer registered for stack '{s}'. Available: {list(_ANALYZERS)}")
    return cls()
