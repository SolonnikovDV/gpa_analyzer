from __future__ import annotations

from detailed.lint.base import BaseLinter
from detailed.lint.postgres_linter import PostgresLinter
from detailed.lint.pyspark_linter import PySparkLinter
from detailed.lint.spark_linter import SparkLinter
from detailed.runtime_registry import normalize_stack


def get_linter(stack: str | None) -> BaseLinter:
    runtime_stack = normalize_stack(stack)
    if runtime_stack == "spark":
        return SparkLinter()
    if runtime_stack == "pyspark":
        return PySparkLinter()
    return PostgresLinter()
