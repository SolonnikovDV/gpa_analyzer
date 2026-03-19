from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class LintIssue:
    severity: str
    rule: str
    title: str
    message: str
    hint: str
    index: Optional[int] = None
    length: int = 1
    token: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    fixes: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "severity": self.severity,
            "rule": self.rule,
            "title": self.title,
            "message": self.message,
            "hint": self.hint,
            "length": max(1, int(self.length or 1)),
        }
        if self.token:
            data["token"] = self.token
        if self.index is not None:
            data["index"] = max(0, int(self.index))
        if self.line is not None:
            data["line"] = self.line
        if self.column is not None:
            data["column"] = self.column
        if self.fixes:
            data["fixes"] = self.fixes
        return data


@dataclass
class LintResult:
    ok: bool
    contains_code: bool
    issues: List[LintIssue] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "ok": self.ok,
            "contains_code": self.contains_code,
            "issues": [issue.to_dict() for issue in self.issues],
        }
        if self.error:
            data["error"] = self.error
        return data


class BaseLinter(Protocol):
    stack: str

    def validate(
        self,
        source_text: str,
        *,
        scenario: str,
        metadata_provider: Any = None,
    ) -> Dict[str, Any]:
        ...

    def complete(
        self,
        source_text: str,
        cursor_index: int,
        *,
        scenario: str,
        conn_string: Optional[str] = None,
    ) -> Dict[str, Any]:
        ...
