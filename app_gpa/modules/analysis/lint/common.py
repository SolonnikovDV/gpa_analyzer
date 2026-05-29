from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .base import LintIssue, LintResult


def index_to_line_column(text: str, index: int) -> Tuple[int, int]:
    """1-based line and column for a character index in ``text``."""
    idx = max(0, min(int(index), len(text)))
    before = text[:idx]
    line = before.count("\n") + 1
    last_nl = before.rfind("\n")
    column = idx - last_nl
    return line, column


def char_index_from_line_column_1based(text: str, line: int, column: int) -> int:
    """Byte/char index in ``text`` from 1-based line and 1-based column (as in sqlglot errors)."""
    lines = str(text).split("\n")
    ln = max(1, int(line))
    col = max(1, int(column))
    idx = 0
    for i in range(ln - 1):
        if i >= len(lines):
            return len(text)
        idx += len(lines[i]) + 1
    if ln - 1 >= len(lines):
        return len(text)
    line_text = lines[ln - 1]
    col0 = min(col - 1, len(line_text))
    return idx + col0


def ast_node_span(text: str, node: Any) -> Optional[Tuple[int, int]]:
    """
    Return (start, end) character indices for an ast.AST node (lineno/col_offset).
    Uses end_lineno/end_col_offset if present (Py3.8+).
    """
    import ast as _ast

    if not isinstance(node, _ast.AST):
        return None
    line1 = getattr(node, "lineno", 1) or 1
    col1 = getattr(node, "col_offset", 0) or 0
    line2 = getattr(node, "end_lineno", None) or line1
    col2 = getattr(node, "end_col_offset", None)
    if col2 is None:
        col2 = col1 + 1
    start = char_index_from_line_column_1based(text, line1, col1 + 1)
    end = char_index_from_line_column_1based(text, line2, col2 + 1)
    return (start, max(end, start + 1))


def issue_from_span(
    text: str,
    start: int,
    end: int,
    rule: str,
    title: str,
    message: str,
    hint: str,
    *,
    severity: str = "warning",
    fixes: Optional[List[Dict[str, Any]]] = None,
) -> LintIssue:
    """Build a lint issue with line/column derived from a half-open ``[start, end)`` span."""
    start_i = max(0, min(int(start), len(text)))
    end_i = max(start_i, min(int(end), len(text)))
    line, col = index_to_line_column(text, start_i)
    span_len = max(1, end_i - start_i)
    return LintIssue(
        severity=severity,
        rule=rule,
        title=title,
        message=message,
        hint=hint,
        index=start_i,
        length=span_len,
        line=line,
        column=col,
        fixes=fixes,
    )


def first_non_whitespace_span(text: str) -> Optional[Tuple[int, int]]:
    m = re.search(r"\S", str(text or ""))
    if not m:
        return None
    p = m.start()
    return p, p + 1


def infer_token_bounds(source_text: str, cursor_index: int) -> Tuple[int, int, str]:
    text = str(source_text or "")
    cursor = max(0, min(int(cursor_index or 0), len(text)))
    left = text[:cursor]
    right = text[cursor:]
    left_match = re.search(r"[A-Za-z0-9_$.]*$", left)
    right_match = re.match(r"^[A-Za-z0-9_$.]*", right)
    start = left_match.start() if left_match else cursor
    end = cursor + (right_match.end() if right_match else 0)
    return start, end, text[start:end]


def make_issue(
    rule: str,
    title: str,
    message: str,
    hint: str,
    *,
    severity: str = "warning",
) -> LintIssue:
    return LintIssue(
        severity=severity,
        rule=rule,
        title=title,
        message=message,
        hint=hint,
    )


def empty_result(rule: str, title: str, message: str, hint: str) -> Dict[str, Any]:
    issue = LintIssue(
        severity="warning",
        rule=rule,
        title=title,
        message=message,
        hint=hint,
        line=1,
        column=1,
        length=1,
        index=0,
    )
    return LintResult(ok=True, contains_code=False, issues=[issue]).to_dict()


def build_keyword_items(
    keywords: Sequence[str],
    source_text: str,
    cursor_index: int,
    *,
    detail: str,
    kind: str = "keyword",
    extra_items: Iterable[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    start, end, token = infer_token_bounds(source_text, cursor_index)
    prefix = token.upper()
    items: List[Dict[str, Any]] = []
    for keyword in keywords:
        if not prefix or keyword.upper().startswith(prefix):
            items.append({
                "text": keyword,
                "displayText": keyword,
                "replace_from": start,
                "replace_to": end,
                "kind": kind,
                "detail": detail,
                "boost": 100,
            })
    if extra_items:
        items.extend(list(extra_items))

    unique: Dict[tuple[str, int, int], Dict[str, Any]] = {}
    for item in items:
        key = (str(item.get("text") or ""), int(item.get("replace_from") or 0), int(item.get("replace_to") or 0))
        if key not in unique or unique[key].get("boost", 0) < item.get("boost", 0):
            unique[key] = item
    ordered = sorted(unique.values(), key=lambda item: (-item.get("boost", 0), str(item.get("text") or "")))
    return {"items": ordered[:40]}
