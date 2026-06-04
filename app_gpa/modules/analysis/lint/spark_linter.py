from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from .base import BaseLinter, LintIssue, LintResult
from .common import (
    build_keyword_items,
    char_index_from_line_column_1based,
    empty_result,
    first_non_whitespace_span,
    infer_token_bounds,
    issue_from_span,
)

SPARK_SQL_KEYWORDS = [
    "SELECT", "FROM", "WHERE", "JOIN", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN",
    "GROUP BY", "ORDER BY", "HAVING", "LIMIT", "WITH", "UNION", "CASE", "WHEN",
    "THEN", "ELSE", "END", "LATERAL VIEW", "EXPLODE", "CACHE TABLE", "DISTRIBUTE BY",
    "SORT BY", "CLUSTER BY", "INSERT OVERWRITE", "CREATE TABLE", "REFRESH TABLE",
]
SPARK_SQL_FUNCTIONS = [
    "explode(", "posexplode(", "collect_list(", "collect_set(", "array_contains(",
    "from_json(", "to_json(", "get_json_object(", "coalesce(", "date_trunc(",
]

_SPARK_DIALECT_TRY: Tuple[str, ...] = ("spark", "databricks")


def _parse_spark_sql_trees(source: str) -> Tuple[str, List[exp.Expression]]:
    """Parse with Spark dialect; fall back to Databricks for edge syntax."""
    last_err: Optional[ParseError] = None
    for dialect in _SPARK_DIALECT_TRY:
        try:
            trees = parse(source, dialect=dialect)
            return dialect, [t for t in trees if t is not None]
        except ParseError as exc:
            last_err = exc
    assert last_err is not None
    raise last_err


def _issue_from_parse_error(text: str, exc: ParseError) -> LintIssue:
    errors = getattr(exc, "errors", None) or []
    if not errors:
        anchor = first_non_whitespace_span(text) or (0, 1)
        return issue_from_span(
            text,
            anchor[0],
            anchor[1],
            "spark-sql-parse-error",
            "Ошибка синтаксиса Spark SQL",
            str(exc).strip() or "Запрос не удалось разобрать парсером Spark SQL.",
            "Проверьте синтаксис в соответствии с документацией Spark SQL.",
            severity="error",
        )
    err = errors[0]
    line = int(err.get("line") or 1)
    col = int(err.get("col") or 1)
    desc = str(err.get("description") or "Синтаксическая ошибка").strip()
    highlight = err.get("highlight")
    start = char_index_from_line_column_1based(text, line, col)
    if isinstance(highlight, str) and highlight:
        end = start + max(1, len(highlight))
    else:
        end = start + 1
    end = min(len(text), end)
    return issue_from_span(
        text,
        start,
        end,
        "spark-sql-parse-error",
        "Ошибка синтаксиса Spark SQL",
        desc,
        "Исправьте фрагмент, на который указывает парсер, и повторите проверку.",
        severity="error",
    )


def _collect_select_star_issues(text: str, trees: Sequence[exp.Expression]) -> List[LintIssue]:
    has_star = False
    for root in trees:
        for sel in root.find_all(exp.Select):
            for proj in sel.expressions:
                if isinstance(proj, exp.Star):
                    has_star = True
                    break
                if isinstance(proj, exp.Column) and isinstance(getattr(proj, "this", None), exp.Star):
                    has_star = True
                    break
            if has_star:
                break
        if has_star:
            break
    if not has_star:
        return []
    return [
        issue_from_span(
            text,
            m.start(),
            m.end(),
            "spark-select-star",
            "SELECT * в Spark может быть дорогим",
            "Широкие выборки в Spark часто увеличивают shuffle и объем чтения.",
            "По возможности перечислите только нужные колонки.",
        )
        for m in re.finditer(r"\bselect\s+\*", text, flags=re.IGNORECASE)
    ]


def _collect_explode_issues(text: str, trees: Sequence[exp.Expression]) -> List[LintIssue]:
    out: List[LintIssue] = []
    for root in trees:
        has_lateral = bool(list(root.find_all(exp.Lateral)))
        explodes = list(root.find_all(exp.Explode))
        if not explodes or has_lateral:
            continue
        matches = list(re.finditer(r"\bexplode\s*\(", text, flags=re.IGNORECASE))
        for i in range(min(len(explodes), len(matches))):
            m = matches[i]
            out.append(
                issue_from_span(
                    text,
                    m.start(),
                    m.end(),
                    "spark-explode-without-lateral-view",
                    "Проверьте использование explode",
                    "В Spark SQL `explode()` часто используется вместе с `LATERAL VIEW`.",
                    "Если нужен разворот массива, проверьте `LATERAL VIEW explode(...) alias AS col`.",
                )
            )
    return out


def _collect_insert_overwrite_issues(text: str, trees: Sequence[exp.Expression]) -> List[LintIssue]:
    out: List[LintIssue] = []
    matches = list(re.finditer(r"\binsert\s+overwrite\b", text, flags=re.IGNORECASE))
    mi = 0
    for root in trees:
        for ins in root.find_all(exp.Insert):
            if not ins.args.get("overwrite"):
                continue
            if ins.args.get("partition") is not None:
                continue
            if mi >= len(matches):
                break
            m = matches[mi]
            mi += 1
            out.append(
                issue_from_span(
                    text,
                    m.start(),
                    m.end(),
                    "spark-insert-overwrite-without-partition",
                    "Проверьте INSERT OVERWRITE",
                    "`INSERT OVERWRITE` может затронуть больше данных, чем ожидается.",
                    "Если таблица партиционирована, проверьте необходимость явного `PARTITION (...)`.",
                )
            )
    return out


class SparkLinter(BaseLinter):
    stack = "spark"

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
                "empty-spark-source",
                "В тексте не найден Spark SQL код",
                "Окно пустое или не содержит конструкций Spark SQL.",
                "Добавьте Spark SQL, например `select * from table_name`.",
            )

        try:
            _dialect, trees = _parse_spark_sql_trees(text)
        except ParseError as exc:
            issue = _issue_from_parse_error(text, exc)
            return LintResult(ok=False, contains_code=True, issues=[issue], error=str(exc)).to_dict()

        issues: List[LintIssue] = []
        issues.extend(_collect_select_star_issues(text, trees))
        issues.extend(_collect_explode_issues(text, trees))
        issues.extend(_collect_insert_overwrite_issues(text, trees))

        return LintResult(ok=True, contains_code=True, issues=issues).to_dict()

    def complete(
        self,
        source_text: str,
        cursor_index: int,
        *,
        scenario: str,
        conn_string: Optional[str] = None,
    ) -> Dict[str, object]:
        start, end, token = infer_token_bounds(source_text, cursor_index)
        prefix = token.upper()
        extra_items = [{
            "text": item,
            "displayText": item,
            "replace_from": start,
            "replace_to": end,
            "kind": "function",
            "detail": "Spark SQL",
            "boost": 115,
        } for item in SPARK_SQL_FUNCTIONS if not prefix or item.upper().startswith(prefix)]
        return build_keyword_items(
            SPARK_SQL_KEYWORDS,
            source_text,
            cursor_index,
            detail="Spark SQL",
            extra_items=extra_items,
        )
