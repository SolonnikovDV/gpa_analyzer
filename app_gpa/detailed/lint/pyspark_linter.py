from __future__ import annotations

import ast
import re
from typing import Any, Dict, List, Optional, Tuple

from detailed.lint.base import BaseLinter, LintIssue, LintResult
from detailed.lint.common import (
    ast_node_span,
    build_keyword_items,
    empty_result,
    first_non_whitespace_span,
    issue_from_span,
)

PYSPARK_HINTS = [
    "spark.read",
    "spark.sql(",
    ".select(",
    ".join(",
    ".groupBy(",
    ".withColumn(",
]
PYSPARK_COMPLETIONS = [
    "spark.read",
    "spark.table(",
    "spark.sql(",
    "df.select(",
    "df.filter(",
    "df.where(",
    "df.join(",
    "df.groupBy(",
    "df.agg(",
    "df.withColumn(",
    "df.drop(",
    "df.orderBy(",
    "df.repartition(",
    "df.cache(",
    "df.persist(",
    "df.show(",
    "df.collect(",
    "df.write",
    "F.col(",
    "F.when(",
    "F.lit(",
    "F.sum(",
    "F.count(",
]


def _contains_pyspark_heuristic(text: str) -> bool:
    return any(h in (text or "") for h in PYSPARK_HINTS)


class _PySparkVisitor(ast.NodeVisitor):
    """Collects risky patterns from Python AST (collect, toPandas, udf)."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.issues: List[Tuple[str, str, str, str, ast.AST]] = []

    def _add(self, rule: str, title: str, message: str, hint: str, node: ast.AST) -> None:
        self.issues.append((rule, title, message, hint, node))

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if attr == "collect":
                self._add(
                    "pyspark-collect-risk",
                    "collect() может быть дорогой операцией",
                    "`collect()` переносит данные на драйвер и может стать узким местом.",
                    "Проверьте, нужен ли полный materialization на драйвере, или можно ограничить выборку.",
                    node.func,
                )
            elif attr == "toPandas":
                self._add(
                    "pyspark-topandas-risk",
                    "toPandas() может выгрузить слишком много данных",
                    "`toPandas()` материализует данные на драйвере и может привести к OOM.",
                    "Перед `toPandas()` проверьте объем данных и при необходимости ограничьте выборку.",
                    node.func,
                )
        elif isinstance(node.func, ast.Name) and node.func.id == "udf":
            self._add(
                "pyspark-python-udf",
                "Обычный Python UDF может замедлять выполнение",
                "Python UDF часто хуже оптимизируется, чем built-in functions или pandas_udf.",
                "Проверьте, можно ли заменить UDF на built-in Spark functions или `pandas_udf`.",
                node.func,
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.generic_visit(node)


class _SparklinessVisitor(ast.NodeVisitor):
    """Detects Spark/DataFrame-related names and attributes."""

    SPARK_NAMES = frozenset({"spark", "SparkSession", "sc", "F", "sqlContext"})
    SPARK_ATTRS = frozenset({
        "read", "sql", "table", "select", "filter", "where", "join", "groupBy",
        "agg", "withColumn", "drop", "orderBy", "repartition", "cache", "persist",
        "show", "collect", "write", "col", "when", "lit", "sum", "count",
    })

    def __init__(self) -> None:
        self.sparky = False

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in self.SPARK_NAMES:
            self.sparky = True
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.attr, str) and node.attr in self.SPARK_ATTRS:
            self.sparky = True
        self.generic_visit(node)


_RULE_REGEX = {
    "pyspark-collect-risk": re.compile(r"\.collect\s*\("),
    "pyspark-topandas-risk": re.compile(r"\.toPandas\s*\("),
    "pyspark-python-udf": re.compile(r"\budf\s*\("),
}


def _issues_from_visitor(
    text: str,
    collected: List[Tuple[str, str, str, str, ast.AST]],
) -> List[LintIssue]:
    out: List[LintIssue] = []
    for rule, title, message, hint, node in collected:
        span = ast_node_span(text, node)
        if span:
            start, end = span
            out.append(issue_from_span(text, start, end, rule, title, message, hint))
        else:
            rx = _RULE_REGEX.get(rule)
            if rx:
                m = rx.search(text)
                if m:
                    out.append(issue_from_span(text, m.start(), m.end(), rule, title, message, hint))
    return out


def _syntax_error_issue(text: str, exc: SyntaxError) -> LintIssue:
    line = getattr(exc, "lineno", 1) or 1
    offset = getattr(exc, "offset", 1) or 1
    msg = (exc.msg or "Синтаксическая ошибка Python.").strip()
    start = 0
    lines = text.split("\n")
    if 1 <= line <= len(lines):
        for i in range(line - 1):
            start += len(lines[i]) + 1
        start = min(start + max(0, offset - 1), len(text))
    end = min(start + 1, len(text))
    return issue_from_span(
        text,
        start,
        end,
        "pyspark-syntax-error",
        "Ошибка синтаксиса Python",
        msg,
        "Исправьте синтаксис в соответствии с Python (PySpark — это Python-код).",
        severity="error",
    )


def _pyspark_weak_signal_result(text: str) -> Dict[str, object]:
    anchor = first_non_whitespace_span(text) or (0, 1)
    return LintResult(
        ok=True,
        contains_code=False,
        issues=[
            issue_from_span(
                text,
                anchor[0],
                anchor[1],
                "pyspark-weak-signal",
                "Похоже, это не PySpark",
                "Не найдены типичные конструкции `spark`/DataFrame API.",
                "Проверьте, что в окне именно PySpark код, а не произвольный текст.",
            )
        ],
    ).to_dict()


class PySparkLinter(BaseLinter):
    stack = "pyspark"

    def validate(
        self,
        source_text: str,
        *,
        scenario: str,
        metadata_provider=None,
    ) -> Dict[str, object]:
        text = str(source_text or "")
        if not text.strip():
            return empty_result(
                "empty-pyspark-source",
                "В тексте не найден PySpark код",
                "Окно пустое или не содержит конструкций PySpark.",
                "Добавьте код вида `spark.read...`, `spark.sql(...)` или DataFrame pipeline.",
            )

        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            issue = _syntax_error_issue(text, exc)
            return LintResult(ok=False, contains_code=True, issues=[issue], error=str(exc)).to_dict()

        sparkliness = _SparklinessVisitor()
        sparkliness.visit(tree)
        if not sparkliness.sparky:
            return _pyspark_weak_signal_result(text)

        visitor = _PySparkVisitor(text)
        visitor.visit(tree)
        issues = _issues_from_visitor(text, visitor.issues)
        return LintResult(ok=True, contains_code=True, issues=issues).to_dict()

    def complete(
        self,
        source_text: str,
        cursor_index: int,
        *,
        scenario: str,
        conn_string: Optional[str] = None,
    ) -> Dict[str, object]:
        return build_keyword_items(
            PYSPARK_COMPLETIONS,
            source_text,
            cursor_index,
            detail="PySpark",
            kind="symbol",
        )
