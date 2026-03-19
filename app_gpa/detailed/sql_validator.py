from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


_APP_GPA_DIR = Path(__file__).resolve().parent.parent
_SQL_FUNCTION_CACHE_PATH = _APP_GPA_DIR / "sql_function_cache.json"
_SQL_FUNCTION_PROFILES_PATH = _APP_GPA_DIR / "sql_function_profiles.json"
_FROM_REGEX = r'\bfrom\b'
_TRAILING_COMMA_REGEX = r',\s*;'


def strip_sql_comments(sql_text: str) -> str:
    text = str(sql_text or "")
    text = re.sub(r'/\*[\s\S]*?\*/', ' ', text)
    text = re.sub(r'--.*$', ' ', text, flags=re.MULTILINE)
    return text.strip()


def sql_line_col_from_index(sql_text: str, index: int) -> Dict[str, int]:
    safe_index = max(0, min(int(index or 0), len(sql_text)))
    before = sql_text[:safe_index]
    line = before.count('\n') + 1
    last_newline = before.rfind('\n')
    column = safe_index + 1 if last_newline < 0 else safe_index - last_newline
    return {"line": line, "column": column}


@dataclass
class SQLValidationIssue:
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
class SQLValidationResult:
    ok: bool
    contains_code: bool
    issues: List[SQLValidationIssue]
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


def _normalize_function_key(schema: str, name: str) -> tuple[str, str]:
    return (str(schema or "").strip().lower(), str(name or "").strip().lower())


def _load_function_entries(path: Path, default_source: str) -> Dict[tuple[str, str], str]:
    try:
        if not path.is_file():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    items = raw.get("functions") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return {}

    entries: Dict[tuple[str, str], str] = {}
    for item in items:
        schema = ""
        name = ""
        source = default_source
        if isinstance(item, dict):
            schema = str(item.get("schema") or "").strip()
            name = str(item.get("name") or "").strip()
            source = str(item.get("source") or default_source).strip() or default_source
        elif isinstance(item, str) and "." in item:
            schema, name = item.split(".", 1)
        if schema and name:
            entries[_normalize_function_key(schema, name)] = source
    return entries


def _save_function_cache(entries: Dict[tuple[str, str], str]) -> None:
    serializable = {
        "functions": [
            {"schema": schema, "name": name, "source": source}
            for (schema, name), source in sorted(entries.items())
        ]
    }
    _SQL_FUNCTION_CACHE_PATH.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _remember_cached_function(schema: str, name: str) -> None:
    key = _normalize_function_key(schema, name)
    entries = _load_function_entries(_SQL_FUNCTION_CACHE_PATH, "cache")
    if key in entries:
        return
    entries[key] = "cache"
    try:
        _save_function_cache(entries)
    except Exception:
        pass


def load_offline_function_registry() -> Dict[tuple[str, str], str]:
    registry: Dict[tuple[str, str], str] = {}
    registry.update(_load_function_entries(_SQL_FUNCTION_CACHE_PATH, "cache"))
    registry.update(_load_function_entries(_SQL_FUNCTION_PROFILES_PATH, "profile"))
    return registry


class SQLMetadataProvider(Protocol):
    def has_function(self, schema: str, name: str) -> Optional[bool]:
        ...

    def has_qualified_reference(self, schema: str, name: str) -> Optional[bool]:
        ...

    def get_function_source(self, schema: str, name: str) -> Optional[str]:
        ...


class NullSQLMetadataProvider:
    def has_function(self, _schema: str, _name: str) -> Optional[bool]:
        return None

    def has_qualified_reference(self, _schema: str, _name: str) -> Optional[bool]:
        return None

    def get_function_source(self, _schema: str, _name: str) -> Optional[str]:
        return None


class OfflineFunctionRegistryProvider:
    def __init__(self, registry: Optional[Dict[tuple[str, str], str]] = None):
        self.registry = registry or load_offline_function_registry()

    def has_function(self, schema: str, name: str) -> Optional[bool]:
        return True if _normalize_function_key(schema, name) in self.registry else None

    def has_qualified_reference(self, _schema: str, _name: str) -> Optional[bool]:
        return None

    def get_function_source(self, schema: str, name: str) -> Optional[str]:
        return self.registry.get(_normalize_function_key(schema, name))


class PostgresMetadataProvider:
    def __init__(self, conn_string: str):
        self.conn_string = conn_string
        self._function_cache: Dict[tuple[str, str], Optional[bool]] = {}

    def _query_exists(self, sql: str, params: tuple[Any, ...]) -> Optional[bool]:
        try:
            import psycopg2

            conn = psycopg2.connect(self.conn_string, connect_timeout=2)
            try:
                conn.autocommit = True
                with conn.cursor() as cursor:
                    cursor.execute("SET statement_timeout TO 1500")
                    cursor.execute(sql, params)
                    row = cursor.fetchone()
                    return bool(row[0]) if row else False
            finally:
                conn.close()
        except Exception:
            return None

    def has_function(self, schema: str, name: str) -> Optional[bool]:
        key = _normalize_function_key(schema, name)
        if key not in self._function_cache:
            self._function_cache[key] = self._query_exists(
                """
                select exists (
                    select 1
                    from pg_proc p
                    join pg_namespace n on n.oid = p.pronamespace
                    where lower(n.nspname) = %s
                      and lower(p.proname) = %s
                )
                """,
                key,
            )
            if self._function_cache[key] is True:
                _remember_cached_function(schema, name)
        return self._function_cache[key]

    def has_qualified_reference(self, _schema: str, _name: str) -> Optional[bool]:
        return None

    def get_function_source(self, schema: str, name: str) -> Optional[str]:
        return "database" if self.has_function(schema, name) is True else None


class CompositeSQLMetadataProvider:
    def __init__(self, providers: List[SQLMetadataProvider]):
        self.providers = providers

    def has_function(self, schema: str, name: str) -> Optional[bool]:
        saw_false = False
        for provider in self.providers:
            value = provider.has_function(schema, name)
            if value is True:
                return True
            if value is False:
                saw_false = True
        return False if saw_false else None

    def has_qualified_reference(self, schema: str, name: str) -> Optional[bool]:
        saw_false = False
        for provider in self.providers:
            value = provider.has_qualified_reference(schema, name)
            if value is True:
                return True
            if value is False:
                saw_false = True
        return False if saw_false else None

    def get_function_source(self, schema: str, name: str) -> Optional[str]:
        for provider in self.providers:
            source = provider.get_function_source(schema, name)
            if source:
                return source
        return None


@dataclass
class SQLValidationContext:
    sql_text: str
    cleaned_sql: str
    parsed_json: Optional[Dict[str, Any]]
    metadata_provider: SQLMetadataProvider


class SQLInspection(Protocol):
    rule: str

    def inspect(self, context: SQLValidationContext) -> List[SQLValidationIssue]:
        ...


def _make_replace_fix(label: str, start: int, end: int, text: str) -> Dict[str, Any]:
    return {
        "label": label,
        "kind": "replace_range",
        "start": max(0, int(start)),
        "end": max(0, int(end)),
        "text": text,
    }


def _scan_sql_structure(sql_text: str) -> Dict[str, Any]:
    stack: List[int] = []
    extra_closing: List[int] = []
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    index = 0
    length = len(sql_text)
    while index < length:
        ch = sql_text[index]
        next_ch = sql_text[index + 1] if index + 1 < length else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            index += 1
            continue

        if in_block_comment:
            if ch == "*" and next_ch == "/":
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue

        if in_single:
            if ch == "'" and next_ch == "'":
                index += 2
                continue
            if ch == "'":
                in_single = False
            index += 1
            continue

        if in_double:
            if ch == '"':
                in_double = False
            index += 1
            continue

        if ch == "-" and next_ch == "-":
            in_line_comment = True
            index += 2
            continue
        if ch == "/" and next_ch == "*":
            in_block_comment = True
            index += 2
            continue
        if ch == "'":
            in_single = True
            index += 1
            continue
        if ch == '"':
            in_double = True
            index += 1
            continue
        if ch == "(":
            stack.append(index)
        elif ch == ")":
            if stack:
                stack.pop()
            else:
                extra_closing.append(index)
        index += 1

    return {"unclosed_opening": stack, "extra_closing": extra_closing}


def make_issue(
    sql_text: str,
    *,
    rule: str,
    title: str,
    message: str,
    hint: str,
    severity: str = "warning",
    index: Optional[int] = None,
    length: int = 1,
    token: Optional[str] = None,
    fixes: Optional[List[Dict[str, Any]]] = None,
) -> SQLValidationIssue:
    line = None
    column = None
    if index is not None:
        pos = sql_line_col_from_index(sql_text, index)
        line = pos["line"]
        column = pos["column"]
    return SQLValidationIssue(
        severity=severity,
        rule=rule,
        title=title,
        message=message,
        hint=hint,
        index=index,
        length=max(1, int(length or 1)),
        token=token,
        line=line,
        column=column,
        fixes=fixes,
    )


def classify_sql_parse_error(sql_text: str, error_text: str) -> SQLValidationIssue:
    err = str(error_text or "").strip() or "Не удалось разобрать SQL."
    lowered = err.lower()
    token_match = re.search(r'at or near "([^"]+)"', err, flags=re.IGNORECASE)
    token = token_match.group(1) if token_match else None
    index_match = re.search(r'at index (\d+)', err, flags=re.IGNORECASE)
    index = int(index_match.group(1)) if index_match else None
    title = "Ошибка синтаксиса PostgreSQL"
    message = err
    hint = "Проверьте участок вокруг проблемного токена и поправьте синтаксис PostgreSQL."
    fixes: List[Dict[str, Any]] = []

    compact = re.sub(r'\s+', ' ', strip_sql_comments(sql_text)).strip().lower()
    if compact.startswith("select from"):
        title = "После SELECT нет выражения"
        message = "После `SELECT` должно быть выражение, колонка или вызов функции."
        hint = "Например: `select schema.name();` или `select column_name from schema.table_name;`."
        select_match = re.search(r'\bselect\b', sql_text, flags=re.IGNORECASE)
        from_match = re.search(_FROM_REGEX, sql_text, flags=re.IGNORECASE)
        if select_match and from_match:
            fixes.append({
                "label": "Вставить * после SELECT",
                "kind": "replace_range",
                "start": select_match.end(),
                "end": from_match.start(),
                "text": " * ",
            })
    elif token == ";":
        if re.search(r'\bfrom\s*;$', compact):
            title = "После FROM не указан источник"
            message = "После `FROM` нужна таблица, view, функция в `FROM` или подзапрос."
            hint = "Например: `select column_name from schema.table_name;`."
            from_match = re.search(_FROM_REGEX, sql_text, flags=re.IGNORECASE)
            if from_match:
                fixes.append({
                    "label": "Подставить schema.table_name",
                    "kind": "replace_range",
                    "start": from_match.end(),
                    "end": len(sql_text.rstrip("; \n\t")),
                    "text": " schema.table_name",
                })
        elif re.search(_TRAILING_COMMA_REGEX, compact):
            title = "Лишняя запятая перед концом запроса"
            message = "В конце списка выражений осталась лишняя запятая."
            hint = "Уберите последнюю запятую перед `;`."
            comma_match = re.search(_TRAILING_COMMA_REGEX, sql_text)
            if comma_match:
                fixes.append({
                    "label": "Убрать запятую перед ;",
                    "kind": "replace_range",
                    "start": comma_match.start(),
                    "end": comma_match.start() + 1,
                    "text": "",
                })
        else:
            title = "Синтаксис обрывается перед `;`"
            message = "Перед завершением запроса не хватает части конструкции."
            hint = "Проверьте выражение перед `;`: часто не хватает аргумента, источника `FROM` или закрывающей скобки."
    elif "end of input" in lowered or "unexpected end of input" in lowered:
        title = "Запрос обрывается раньше времени"
        message = "PostgreSQL дошел до конца текста раньше, чем конструкция была завершена."
        hint = "Проверьте баланс скобок, закрытие строк, наличие `FROM`, `THEN`, `END` и других обязательных частей."
    elif token == ")":
        title = "Лишняя закрывающая скобка"
        message = "Найдена закрывающая скобка без корректного открывающего контекста."
        hint = "Проверьте, что каждая `)` соответствует своей `(`."
    elif token == ",":
        title = "Лишняя или неожиданная запятая"
        message = "Запятая стоит в месте, где PostgreSQL ожидал выражение."
        hint = "Уберите лишнюю запятую или добавьте пропущенное выражение между элементами списка."
        if index is not None:
            fixes.append({
                "label": "Убрать запятую",
                "kind": "replace_range",
                "start": index,
                "end": index + 1,
                "text": "",
            })
    elif token:
        title = f"Проблема около `{token}`"
        message = f"PostgreSQL не смог корректно разобрать участок рядом с `{token}`."
        hint = f"Проверьте, на своем ли месте `{token}`, и хватает ли рядом операторов, скобок и аргументов."

    return make_issue(
        sql_text,
        rule="postgres-parse-error",
        title=title,
        message=message,
        hint=hint,
        index=index,
        length=len(token) if token else 1,
        token=token,
        fixes=fixes or None,
    )


class MissingSelectExpressionInspection:
    rule = "missing-select-expression"

    def inspect(self, context: SQLValidationContext) -> List[SQLValidationIssue]:
        match = re.search(r'\bselect\b(?P<gap>\s*)' + _FROM_REGEX, context.sql_text, flags=re.IGNORECASE)
        if not match:
            return []
        select_match = re.search(r'\bselect\b', context.sql_text, flags=re.IGNORECASE)
        from_match = re.search(_FROM_REGEX, context.sql_text, flags=re.IGNORECASE)
        if not select_match or not from_match:
            return []
        return [make_issue(
            context.sql_text,
            rule=self.rule,
            title="После SELECT нет выражения",
            message="После `SELECT` должно быть выражение, колонка или вызов функции.",
            hint="Добавьте список полей, `*` или вызов функции перед `FROM`.",
            index=from_match.start(),
            length=max(1, from_match.end() - from_match.start()),
            token="FROM",
            fixes=[_make_replace_fix("Вставить * после SELECT", select_match.end(), from_match.start(), " * ")],
        )]


class MissingFromTargetInspection:
    rule = "missing-from-target"

    def inspect(self, context: SQLValidationContext) -> List[SQLValidationIssue]:
        match = re.search(_FROM_REGEX + r'(?P<tail>\s*)(?P<terminator>;?\s*)$', context.sql_text, flags=re.IGNORECASE)
        if not match:
            return []
        from_match = re.search(_FROM_REGEX, context.sql_text, flags=re.IGNORECASE)
        if not from_match:
            return []
        insert_end = len(context.sql_text.rstrip("; \n\t"))
        return [make_issue(
            context.sql_text,
            rule=self.rule,
            title="После FROM не указан источник",
            message="После `FROM` нужна таблица, view, функция в `FROM` или подзапрос.",
            hint="Укажите источник данных, например `schema.table_name`.",
            index=from_match.start(),
            length=max(1, from_match.end() - from_match.start()),
            token="FROM",
            fixes=[_make_replace_fix("Подставить schema.table_name", from_match.end(), insert_end, " schema.table_name")],
        )]


class TrailingCommaInspection:
    rule = "trailing-comma-before-terminator"

    def inspect(self, context: SQLValidationContext) -> List[SQLValidationIssue]:
        match = re.search(_TRAILING_COMMA_REGEX, context.sql_text)
        if not match:
            return []
        return [make_issue(
            context.sql_text,
            rule=self.rule,
            title="Лишняя запятая перед концом запроса",
            message="В конце списка выражений осталась лишняя запятая.",
            hint="Уберите последнюю запятую перед `;`.",
            index=match.start(),
            length=1,
            token=",",
            fixes=[_make_replace_fix("Убрать запятую перед ;", match.start(), match.start() + 1, "")],
        )]


class UnbalancedParenthesesInspection:
    rule = "unbalanced-parentheses"

    def inspect(self, context: SQLValidationContext) -> List[SQLValidationIssue]:
        structure = _scan_sql_structure(context.sql_text)
        extra_closing = structure.get("extra_closing") or []
        unclosed_opening = structure.get("unclosed_opening") or []
        issues: List[SQLValidationIssue] = []

        if extra_closing:
            index = int(extra_closing[0])
            issues.append(make_issue(
                context.sql_text,
                rule=self.rule,
                title="Лишняя закрывающая скобка",
                message="Найдена закрывающая скобка без корректного открывающего контекста.",
                hint="Удалите лишнюю `)` или добавьте пропущенную открывающую скобку раньше по выражению.",
                index=index,
                length=1,
                token=")",
                fixes=[_make_replace_fix("Удалить лишнюю )", index, index + 1, "")],
            ))

        if unclosed_opening:
            index = int(unclosed_opening[-1])
            issues.append(make_issue(
                context.sql_text,
                rule=self.rule,
                title="Не хватает закрывающей скобки",
                message="Открывающая скобка не была закрыта до конца запроса.",
                hint="Добавьте `)` в конце выражения или закройте нужный блок раньше.",
                index=index,
                length=1,
                token="(",
                fixes=[_make_replace_fix("Добавить закрывающую ) в конец", len(context.sql_text), len(context.sql_text), ")")],
            ))

        return issues


class MissingFunctionParenthesesInspection:
    rule = "missing-function-parentheses"

    @staticmethod
    def _extract_qualified_name(column_ref: Dict[str, Any]) -> Optional[List[str]]:
        fields = column_ref.get("fields") or []
        names: List[str] = []
        for field in fields:
            string_field = field.get("String") if isinstance(field, dict) else None
            if not string_field:
                return None
            value = string_field.get("sval")
            if not value or value == "*":
                return None
            names.append(str(value))
        return names if len(names) == 2 else None

    def inspect(self, context: SQLValidationContext) -> List[SQLValidationIssue]:
        if not context.parsed_json:
            return []
        issues: List[SQLValidationIssue] = []
        for raw_stmt in context.parsed_json.get("stmts", []):
            stmt = (raw_stmt or {}).get("stmt") or {}
            select_stmt = stmt.get("SelectStmt")
            if not select_stmt:
                continue
            if select_stmt.get("fromClause"):
                continue
            for target in select_stmt.get("targetList") or []:
                res_target = (target or {}).get("ResTarget") or {}
                column_ref = ((res_target.get("val") or {}).get("ColumnRef")) or {}
                if not column_ref:
                    continue
                parts = self._extract_qualified_name(column_ref)
                if not parts:
                    continue
                schema, name = parts
                has_function = context.metadata_provider.has_function(schema, name)
                has_reference = context.metadata_provider.has_qualified_reference(schema, name)
                if has_reference is True and has_function is False:
                    continue

                full_name = f"{schema}.{name}"
                location = column_ref.get("location")
                if not isinstance(location, int) or location < 0:
                    location = context.sql_text.lower().find(full_name.lower())
                function_source = context.metadata_provider.get_function_source(schema, name)
                if function_source == "database":
                    message = f"Найдена функция `{full_name}`, но она записана без скобок."
                    hint = f"Используйте вызов функции: `select {full_name}();`."
                elif function_source == "profile":
                    message = f"Функция `{full_name}` найдена в локальном профиле функций, но записана без скобок."
                    hint = f"Если используется профильная функция, вызов должен быть таким: `select {full_name}();`."
                elif function_source == "cache":
                    message = f"Функция `{full_name}` найдена в локальном кэше известных функций, но записана без скобок."
                    hint = f"Если используется закэшированная функция, вызов должен быть таким: `select {full_name}();`."
                else:
                    message = f"Внутри скрипта выражение `{full_name}` выглядит как вызов функции, но записано без `()`."
                    hint = f"Если здесь должен вызываться объект-функция, используйте `select {full_name}();`."
                fixes = None
                if isinstance(location, int) and location >= 0:
                    fixes = [{
                        "label": f"Заменить на {full_name}()",
                        "kind": "replace_range",
                        "start": location,
                        "end": location + len(full_name),
                        "text": f"{full_name}()",
                    }]
                issues.append(make_issue(
                    context.sql_text,
                    rule=self.rule,
                    title="Похоже на вызов функции без скобок",
                    message=message,
                    hint=hint,
                    index=location if isinstance(location, int) and location >= 0 else None,
                    length=len(full_name),
                    token=full_name,
                    fixes=fixes,
                ))
        return issues


DEFAULT_SQL_TEXT_INSPECTIONS: List[SQLInspection] = [
    MissingSelectExpressionInspection(),
    MissingFromTargetInspection(),
    TrailingCommaInspection(),
    UnbalancedParenthesesInspection(),
]


DEFAULT_SQL_AST_INSPECTIONS: List[SQLInspection] = [
    MissingFunctionParenthesesInspection(),
]


def _pglast_parse_sql_json_dict(sql_text: str) -> Optional[Dict[str, Any]]:
    """
    Run pglast SQL parse and return the libpg_query JSON tree as a dict.

    In pglast v5+ ``parse_sql_json`` lives in ``pglast.parser``, not on the
    ``pglast`` package root (calling ``pglast.parse_sql_json`` raises
    AttributeError). If JSON helpers are missing, returns None (AST-based
    inspections are skipped; text-based inspections still run).
    """
    import pglast

    pglast.parse_sql(sql_text)
    parse_sql_json_fn = None
    try:
        from pglast.parser import parse_sql_json as parse_sql_json_fn  # type: ignore[attr-defined]
    except ImportError:
        parse_sql_json_fn = getattr(pglast, "parse_sql_json", None)
    if parse_sql_json_fn is None:
        return None
    return json.loads(parse_sql_json_fn(sql_text))


def validate_sql_advisory(
    sql_text: str,
    metadata_provider: Optional[SQLMetadataProvider] = None,
) -> Dict[str, Any]:
    provider = metadata_provider or OfflineFunctionRegistryProvider()
    cleaned = strip_sql_comments(sql_text)
    if not cleaned:
        result = SQLValidationResult(
            ok=True,
            contains_code=False,
            issues=[
                make_issue(
                    sql_text,
                    rule="empty-sql",
                    title="В тексте не найден SQL-код",
                    message="После удаления комментариев в окне не осталось SQL-конструкций.",
                    hint="Добавьте SQL-оператор, например `select 1;` или `select schema.name();`.",
                )
            ],
        )
        return result.to_dict()

    try:
        parsed_json = _pglast_parse_sql_json_dict(sql_text)
    except Exception as exc:
        context = SQLValidationContext(
            sql_text=sql_text,
            cleaned_sql=cleaned,
            parsed_json=None,
            metadata_provider=provider,
        )
        issues: List[SQLValidationIssue] = []
        for inspection in DEFAULT_SQL_TEXT_INSPECTIONS:
            issues.extend(inspection.inspect(context))
        if not issues:
            issues = [classify_sql_parse_error(sql_text, str(exc))]
        issues.sort(key=lambda issue: (issue.index is None, issue.index if issue.index is not None else 10 ** 9, issue.rule))
        result = SQLValidationResult(
            ok=False,
            contains_code=True,
            issues=issues,
            error=str(exc),
        )
        return result.to_dict()

    context = SQLValidationContext(
        sql_text=sql_text,
        cleaned_sql=cleaned,
        parsed_json=parsed_json,
        metadata_provider=provider,
    )
    issues: List[SQLValidationIssue] = []
    for inspection in DEFAULT_SQL_TEXT_INSPECTIONS + DEFAULT_SQL_AST_INSPECTIONS:
        issues.extend(inspection.inspect(context))
    issues.sort(key=lambda issue: (issue.index is None, issue.index if issue.index is not None else 10 ** 9, issue.rule))

    result = SQLValidationResult(
        ok=True,
        contains_code=True,
        issues=issues,
    )
    return result.to_dict()
