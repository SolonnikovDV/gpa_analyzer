from __future__ import annotations

from .base import BaseLinter
from .postgres_linter import PostgresLinter
from .pyspark_linter import PySparkLinter
from .spark_linter import SparkLinter
from ..runtime_registry import normalize_stack


def get_linter(stack: str | None) -> BaseLinter:
    runtime_stack = normalize_stack(stack)
    if runtime_stack == "spark":
        return SparkLinter()
    if runtime_stack == "pyspark":
        return PySparkLinter()
    return PostgresLinter()
