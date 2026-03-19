from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from detailed.sql_validator import load_offline_function_registry


SQL_KEYWORDS = [
    "SELECT", "FROM", "WHERE", "JOIN", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN",
    "FULL JOIN", "ON", "GROUP BY", "ORDER BY", "HAVING", "LIMIT", "OFFSET",
    "INSERT INTO", "UPDATE", "DELETE FROM", "VALUES", "RETURNING", "WITH",
    "CREATE", "CREATE OR REPLACE", "FUNCTION", "RETURNS", "LANGUAGE", "BEGIN",
    "END", "DECLARE", "AS", "DISTINCT", "UNION", "ALL", "CASE", "WHEN", "THEN",
    "ELSE", "END", "EXISTS", "IN", "IS NULL", "IS NOT NULL", "LIKE", "ILIKE",
]

SQL_OPERATORS = [
    "AND", "OR", "NOT", "=", "<>", "!=", ">", "<", ">=", "<=", "||", "IN", "LIKE", "ILIKE",
]


def _infer_token_bounds(sql_text: str, cursor_index: int) -> Tuple[int, int, str]:
    left = sql_text[:cursor_index]
    right = sql_text[cursor_index:]
    left_match = re.search(r"[A-Za-z0-9_$]*$", left)
    right_match = re.match(r"^[A-Za-z0-9_$]*", right)
    start = left_match.start() if left_match else cursor_index
    end = cursor_index + (right_match.end() if right_match else 0)
    return start, end, sql_text[start:end]


def _extract_from_tables(sql_text: str) -> Dict[str, Tuple[Optional[str], str]]:
    mappings: Dict[str, Tuple[Optional[str], str]] = {}
    pattern = re.compile(
        r"\b(?:from|join)\s+((?:(?P<schema>[A-Za-z_][\w$]*)\.)?(?P<table>[A-Za-z_][\w$]*))"
        r"(?:\s+(?:as\s+)?(?P<alias>[A-Za-z_][\w$]*))?",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(sql_text):
        schema = match.group("schema")
        table = match.group("table")
        alias = match.group("alias")
        key = (alias or table).lower()
        mappings[key] = (schema.lower() if schema else None, table.lower())
    return mappings


def _query_columns_for_table(cursor, schema: Optional[str], table: str, prefix: str) -> List[str]:
    if schema:
        cursor.execute(
            """
            select lower(column_name)
            from information_schema.columns
            where lower(table_schema) = %s
              and lower(table_name) = %s
              and lower(column_name) like %s
            order by 1
            limit 30
            """,
            (schema, table, prefix + "%"),
        )
    else:
        cursor.execute(
            """
            select lower(column_name)
            from information_schema.columns
            where lower(table_name) = %s
              and lower(column_name) like %s
            order by 1
            limit 30
            """,
            (table, prefix + "%"),
        )
    return [str(row[0]) for row in cursor.fetchall()]


def _infer_value_context(sql_text: str, cursor_index: int) -> Optional[Dict[str, Any]]:
    left = sql_text[:cursor_index]
    match = re.search(
        r"([A-Za-z_][A-Za-z0-9_$]*(?:\.[A-Za-z_][A-Za-z0-9_$]*)?)\s*(=|like|ilike)\s*'([^']*)$",
        left,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    identifier = match.group(1)
    prefix = match.group(3)
    start = cursor_index - len(prefix)
    table_map = _extract_from_tables(sql_text)
    parts = identifier.split(".")
    schema = None
    table = None
    column = None
    if len(parts) == 3:
        schema, table, column = [part.lower() for part in parts]
    elif len(parts) == 2:
        left_part, right_part = [part.lower() for part in parts]
        if left_part in table_map:
            schema, table = table_map[left_part]
            column = right_part
        else:
            table = left_part
            column = right_part
    elif len(parts) == 1:
        column = parts[0].lower()
        first_table = next(iter(table_map.values()), None)
        if first_table:
            schema, table = first_table
    if not table or not column:
        return None
    return {
        "schema": schema,
        "table": table,
        "column": column,
        "prefix": prefix,
        "start": start,
        "end": cursor_index,
    }


def _infer_dot_context(sql_text: str, cursor_index: int) -> Optional[Dict[str, Any]]:
    left = sql_text[:cursor_index]
    match = re.search(r"((?:[A-Za-z_][A-Za-z0-9_$]*\.)+)([A-Za-z_][A-Za-z0-9_$]*)?$", left)
    if not match:
        return None
    parts = [part for part in match.group(1).split(".") if part]
    prefix = match.group(2) or ""
    start = cursor_index - len(prefix)
    return {"parts": [part.lower() for part in parts], "prefix": prefix.lower(), "start": start, "end": cursor_index}


def _build_suggestion(text: str, start: int, end: int, kind: str, detail: str = "", boost: int = 100) -> Dict[str, Any]:
    return {
        "text": text,
        "displayText": text,
        "replace_from": start,
        "replace_to": end,
        "kind": kind,
        "detail": detail,
        "boost": boost,
    }


def _keyword_suggestions(prefix: str, start: int, end: int) -> List[Dict[str, Any]]:
    prefix_upper = prefix.upper()
    suggestions = []
    for keyword in SQL_KEYWORDS + SQL_OPERATORS:
        if not prefix or keyword.startswith(prefix_upper):
            suggestions.append(_build_suggestion(keyword, start, end, "keyword", "SQL"))
    return suggestions


def _offline_function_suggestions(prefix: str, start: int, end: int) -> List[Dict[str, Any]]:
    suggestions = []
    for (schema, name), source in load_offline_function_registry().items():
        candidate = f"{schema}.{name}()"
        if not prefix or candidate.lower().startswith(prefix.lower()) or name.startswith(prefix.lower()):
            suggestions.append(_build_suggestion(candidate, start, end, "function", source, 120))
    return suggestions


def _query_db_suggestions(conn_string: str, sql_text: str, cursor_index: int) -> List[Dict[str, Any]]:
    try:
        import psycopg2
        from psycopg2 import sql as psql
    except Exception:
        return []

    start, end, token = _infer_token_bounds(sql_text, cursor_index)
    prefix = token.lower()
    dot_context = _infer_dot_context(sql_text, cursor_index)
    value_context = _infer_value_context(sql_text, cursor_index)
    table_map = _extract_from_tables(sql_text)

    suggestions: List[Dict[str, Any]] = []
    try:
        conn = psycopg2.connect(conn_string, connect_timeout=2)
        try:
            conn.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute("SET statement_timeout TO 1500")
                if value_context:
                    identifier = psql.Identifier(value_context["column"])
                    table_ident = (
                        psql.Identifier(value_context["schema"], value_context["table"])
                        if value_context["schema"]
                        else psql.Identifier(value_context["table"])
                    )
                    query = psql.SQL(
                        "select distinct {col}::text from {table} "
                        "where {col} is not null and {col}::text ilike %s "
                        "order by 1 limit 8"
                    ).format(col=identifier, table=table_ident)
                    cursor.execute(query, (value_context["prefix"] + "%",))
                    for row in cursor.fetchall():
                        if row and row[0] is not None:
                            suggestions.append(_build_suggestion(str(row[0]), value_context["start"], value_context["end"], "value", "DB value", 140))
                    return suggestions

                if dot_context:
                    parts = dot_context["parts"]
                    dot_prefix = dot_context["prefix"]
                    if len(parts) == 1:
                        base = parts[0]
                        if base in table_map:
                            schema_name, table_name = table_map[base]
                            for column_name in _query_columns_for_table(cursor, schema_name, table_name, dot_prefix):
                                suggestions.append(_build_suggestion(str(column_name), dot_context["start"], dot_context["end"], "column", base, 140))
                            return suggestions
                        cursor.execute(
                            """
                            select lower(table_schema) || '.' || lower(table_name), 'table'
                            from information_schema.tables
                            where lower(table_schema) = %s and lower(table_name) like %s
                            union all
                            select lower(routine_schema) || '.' || lower(routine_name) || '()', 'function'
                            from information_schema.routines
                            where lower(routine_schema) = %s and lower(routine_name) like %s
                            limit 20
                            """,
                            (base, dot_prefix + "%", base, dot_prefix + "%"),
                        )
                        for text, kind in cursor.fetchall():
                            suggestions.append(_build_suggestion(str(text), dot_context["start"], dot_context["end"], str(kind), "DB", 130))
                        for column_name in _query_columns_for_table(cursor, None, base, dot_prefix):
                            suggestions.append(_build_suggestion(str(column_name), dot_context["start"], dot_context["end"], "column", base, 130))
                        return suggestions
                    if len(parts) >= 2:
                        schema_name = parts[0]
                        table_name = parts[1]
                        for column_name in _query_columns_for_table(cursor, schema_name, table_name, dot_prefix):
                            suggestions.append(_build_suggestion(str(column_name), dot_context["start"], dot_context["end"], "column", schema_name + "." + table_name, 135))
                        return suggestions

                if table_map:
                    for alias, (schema_name, table_name) in table_map.items():
                        for column_name in _query_columns_for_table(cursor, schema_name, table_name, prefix):
                            suggestions.append(_build_suggestion(str(column_name), start, end, "column", alias, 125))
                            suggestions.append(_build_suggestion(alias + "." + str(column_name), start, end, "column", table_name, 120))

                cursor.execute(
                    """
                    select lower(table_schema) || '.' || lower(table_name), 'table'
                    from information_schema.tables
                    where lower(table_name) like %s
                    union all
                    select lower(routine_schema) || '.' || lower(routine_name) || '()', 'function'
                    from information_schema.routines
                    where lower(routine_name) like %s
                    union all
                    select lower(column_name), 'column'
                    from information_schema.columns
                    where lower(column_name) like %s
                    limit 40
                    """,
                    (prefix + "%", prefix + "%", prefix + "%"),
                )
                for text, kind in cursor.fetchall():
                    suggestions.append(_build_suggestion(str(text), start, end, str(kind), "DB", 110))
        finally:
            conn.close()
    except Exception:
        return []
    return suggestions


def complete_sql(
    sql_text: str,
    cursor_index: int,
    *,
    validation_mode: str,
    conn_string: Optional[str] = None,
) -> Dict[str, Any]:
    start, end, token = _infer_token_bounds(sql_text, cursor_index)
    suggestions = []
    suggestions.extend(_keyword_suggestions(token, start, end))
    suggestions.extend(_offline_function_suggestions(token, start, end))
    metadata_allowed = validation_mode in {"hybrid", "analytics", "logic"}
    if metadata_allowed and conn_string:
        suggestions.extend(_query_db_suggestions(conn_string, sql_text, cursor_index))

    unique: Dict[tuple[str, int, int], Dict[str, Any]] = {}
    for item in suggestions:
        key = (item["text"], item["replace_from"], item["replace_to"])
        if key not in unique or unique[key].get("boost", 0) < item.get("boost", 0):
            unique[key] = item
    ordered = sorted(unique.values(), key=lambda item: (-item.get("boost", 0), item["text"]))
    return {"items": ordered[:40]}
