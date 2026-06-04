"""Человекочитаемая подпись анализируемого объекта для сводки UI."""
from __future__ import annotations

import re
from typing import Optional, Tuple

_UNKNOWN_NAMES = frozenset({"", "unknown", "n/a", "na", "—", "-", "none", "null"})


def _parse_function_name_from_ddl(ddl: str) -> str:
    if not ddl or not ddl.strip():
        return ""
    m = re.search(
        r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+"
        r"((?:\"[^\"]+\"|[a-zA-Z_]\w*)(?:\s*\.\s*(?:\"[^\"]+\"|[a-zA-Z_]\w*))*)",
        ddl,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return ""
    qual = m.group(1).strip()
    parts = re.split(r"\s*\.\s*", qual)
    last = parts[-1].strip().strip('"')
    return last or ""


def _infer_input_type(ddl: str) -> str:
    ddl_u = (ddl or "").strip().upper()
    if not ddl_u:
        return "query"
    function_markers = (
        "CREATE OR REPLACE FUNCTION",
        "CREATE FUNCTION",
        "CREATE PROCEDURE",
        "CREATE OR REPLACE PROCEDURE",
        "RETURNS",
        "LANGUAGE PLPGSQL",
        "LANGUAGE SQL",
        "AS $$",
        "AS $",
    )
    if any(marker in ddl_u for marker in function_markers):
        return "function"
    if re.match(r"^\s*DO\s+\$", ddl, re.IGNORECASE):
        return "function"
    return "query"


def _is_anonymous_function(ddl: str, function_name: str) -> bool:
    fn_l = str(function_name or "").strip().lower()
    if fn_l and fn_l not in _UNKNOWN_NAMES:
        return False
    ddl_s = (ddl or "").strip()
    ddl_u = ddl_s.upper()
    if not ddl_s:
        return fn_l in _UNKNOWN_NAMES or not fn_l
    if re.match(r"^\s*DO\s+\$", ddl_s, re.IGNORECASE):
        return True
    if re.match(r"^\s*BEGIN\b", ddl_s, re.IGNORECASE) and "CREATE" not in ddl_u[:300]:
        return True
    if "CREATE" not in ddl_u and ("RETURN QUERY" in ddl_u or "LANGUAGE PLPGSQL" in ddl_u):
        return True
    if "CREATE" in ddl_u and ("FUNCTION" in ddl_u or "PROCEDURE" in ddl_u):
        return True
    return True


def resolve_object_display_label(
    input_type: Optional[str],
    function_name: Optional[str],
    ddl: Optional[str] = None,
) -> str:
    """
    Подпись для блока «Объект»:
    - именованная функция → имя;
    - анонимный блок / функция без имени → «анонимная функция»;
    - запрос → «запрос».
    """
    ddl_text = ddl or ""
    it = (input_type or "").strip().lower()
    if not it:
        it = _infer_input_type(ddl_text)

    if it not in ("function",):
        if ddl_text and _infer_input_type(ddl_text) == "function":
            it = "function"
        else:
            return "запрос"

    fn = str(function_name or "").strip()
    if fn.startswith('"') and fn.endswith('"'):
        fn = fn[1:-1]
    fn_l = fn.lower()

    if fn_l in _UNKNOWN_NAMES and ddl_text:
        parsed = _parse_function_name_from_ddl(ddl_text)
        if parsed:
            fn = parsed
            fn_l = fn.lower()

    if fn and fn_l not in _UNKNOWN_NAMES:
        return fn

    if _is_anonymous_function(ddl_text, fn):
        return "анонимная функция"

    return "анонимная функция"


def resolve_object_display_from_discovery(discovery: dict, ddl: Optional[str] = None) -> str:
    if not discovery:
        return "запрос"
    cached = discovery.get("object_display")
    if cached:
        return str(cached)
    return resolve_object_display_label(
        discovery.get("input_type"),
        discovery.get("function"),
        ddl,
    )
