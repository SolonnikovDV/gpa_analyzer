# ====================================================================
# Файл: detailed/execute_parser.py (исправленная версия)
# ====================================================================
"""
Модуль для разбора и подстановки в EXECUTE ... FORMAT ... в PL/pgSQL.
Позволяет получить итоговый SQL для последующего анализа.
Включает обработку SELECT INTO с парсингом функций агрегации.
"""

import re
from typing import Dict, List, Optional, Tuple, Any


class ExecuteParser:
    """
    Парсер для EXECUTE с поддержкой format() и USING.
    Преобразует динамический SQL в статический, подставляя значения переменных.
    """

    @staticmethod
    def parse(execute_stmt: str, variables: Dict[str, str]) -> Optional[str]:
        stmt = execute_stmt.strip().rstrip(';')
        sql = ExecuteParser._parse_using(stmt, variables)
        if sql is not None:
            return sql
        sql = ExecuteParser._parse_format(stmt, variables)
        if sql is not None:
            return sql
        return None

    @staticmethod
    def _parse_using(stmt: str, variables: Dict[str, str]) -> Optional[str]:
        pattern = r"EXECUTE\s+'((?:[^']|'')*)'\s+USING\s+(.+)"
        match = re.search(pattern, stmt, re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        sql_template = match.group(1).replace("''", "'")
        args_part = match.group(2).strip()
        args = ExecuteParser._split_args(args_part)
        substituted_args = []
        for arg in args:
            arg_clean = ExecuteParser._replace_variables_in_arg(arg, variables)
            substituted_args.append(arg_clean)
        final_sql = sql_template
        for i, arg_val in enumerate(substituted_args, 1):
            final_sql = final_sql.replace(f"${i}", arg_val)
        return final_sql

    @staticmethod
    def _parse_format(stmt: str, variables: Dict[str, str]) -> Optional[str]:
        pattern = r"EXECUTE\s+format\(\s*'((?:[^']|'')*)'\s*,\s*(.+)\)"
        match = re.search(pattern, stmt, re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        format_template = match.group(1).replace("''", "'")
        args_part = match.group(2).strip()
        args = ExecuteParser._split_args(args_part)
        substituted_args = []
        for arg in args:
            arg_clean = ExecuteParser._replace_variables_in_arg(arg, variables)
            substituted_args.append(arg_clean)
        final_sql = ExecuteParser._apply_format_placeholders(format_template, substituted_args)
        return final_sql

    @staticmethod
    def _split_args(args_part: str) -> List[str]:
        args = []
        current = []
        depth = 0
        in_string = False
        i = 0
        n = len(args_part)
        while i < n:
            ch = args_part[i]
            if ch == "'" and (i == 0 or args_part[i-1] != '\\'):
                in_string = not in_string
                current.append(ch)
            elif ch == '(' and not in_string:
                depth += 1
                current.append(ch)
            elif ch == ')' and not in_string:
                depth -= 1
                current.append(ch)
            elif ch == ',' and depth == 0 and not in_string:
                arg = ''.join(current).strip()
                if arg:
                    args.append(arg)
                current = []
            else:
                current.append(ch)
            i += 1
        if current:
            arg = ''.join(current).strip()
            if arg:
                args.append(arg)
        return args

    @staticmethod
    def _replace_variables_in_arg(arg: str, variables: Dict[str, str]) -> str:
        sorted_vars = sorted(variables.items(), key=lambda x: -len(x[0]))
        result = arg
        for var_name, var_value in sorted_vars:
            if var_value in (None, 'NULL', ''):
                continue
            pattern = r'\b' + re.escape(var_name) + r'\b'
            result = re.sub(pattern, var_value, result)
        return result

    @staticmethod
    def _apply_format_placeholders(template: str, args: List[str]) -> str:
        def replace_numbered(match):
            num = int(match.group(1))
            spec = match.group(2)
            if num < 1 or num > len(args):
                return match.group(0)
            return ExecuteParser._format_arg(args[num-1], spec)
        template = re.sub(r'%(\d+)\$([ILs])', replace_numbered, template)
        arg_index = 0
        result = []
        i = 0
        n = len(template)
        while i < n:
            if template[i] == '%' and i+1 < n and template[i+1] in ('I', 'L', 's'):
                if arg_index >= len(args):
                    result.append(template[i:i+2])
                    i += 2
                else:
                    spec = template[i+1]
                    formatted = ExecuteParser._format_arg(args[arg_index], spec)
                    result.append(formatted)
                    arg_index += 1
                    i += 2
            else:
                result.append(template[i])
                i += 1
        return ''.join(result)

    @staticmethod
    def _format_arg(arg: str, spec: str) -> str:
        if arg == 'NULL' or arg is None:
            return 'NULL'
        if spec == 'I':
            escaped = arg.replace('"', '""')
            return f'"{escaped}"'
        elif spec == 'L':
            escaped = arg.replace("'", "''")
            return f"'{escaped}'"
        else:  # 's'
            return arg

    # =========================================================================
    # ОБРАБОТКА SELECT INTO ДЛЯ ПЕРЕМЕННЫХ
    # =========================================================================

    @staticmethod
    def parse_select_into(stmt: str, variables: Dict[str, str], var_types: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Парсит SELECT INTO блок и модифицирует его, добавляя COALESCE с дефолтами.
        Возвращает словарь с переменными и SQL без INTO.
        """
        result_vars = ExecuteParser._parse_select_into_vars(stmt)
        if not result_vars:
            return {}
        agg_functions = ExecuteParser._extract_agg_functions(stmt)
        # Модифицируем SELECT, добавляя COALESCE
        modified_sql = ExecuteParser._add_coalesce_defaults(stmt, result_vars, agg_functions, var_types)
        # Удаляем INTO clause
        sql_without_into = ExecuteParser._remove_into_clause(modified_sql)
        return {
            'variables': result_vars,
            'sql_without_into': sql_without_into,
            'agg_functions': agg_functions
        }

    @staticmethod
    def _parse_select_into_vars(stmt: str) -> List[str]:
        """
        Извлекает список переменных из SELECT ... INTO ... clause.
        """
        match = re.search(r'\bINTO\s+', stmt, re.IGNORECASE)
        if not match:
            return []
        into_start = match.end()
        after_into = stmt[into_start:]
        # Ищем первое ключевое слово после INTO
        kw_match = re.search(r'\b(FROM|WHERE|GROUP|ORDER|LIMIT|RETURNING)\b', after_into, re.IGNORECASE)
        if kw_match:
            var_part = after_into[:kw_match.start()].strip()
        else:
            var_part = after_into.strip()
            # удаляем точку с запятой, если есть
            if var_part.endswith(';'):
                var_part = var_part[:-1].strip()
        # Нормализуем пробелы
        var_part = re.sub(r'\s+', ' ', var_part)
        # Разделяем по запятым
        variables = [v.strip() for v in var_part.split(',') if v.strip()]
        return variables

    @staticmethod
    def _extract_agg_functions(stmt: str) -> Dict[int, str]:
        """
        Извлекает агрегирующие функции из SELECT ... INTO clause.
        Возвращает словарь {позиция_переменной: 'функция'}
        """
        match = re.search(r'\bSELECT\s+(.*?)\s+INTO\b', stmt, re.IGNORECASE | re.DOTALL)
        if not match:
            return {}
        select_part = match.group(1).strip()
        # Разделяем на элементы списка выборки, учитывая вложенные скобки
        parts = ExecuteParser._split_select_items(select_part)
        agg_map = {}
        for idx, part in enumerate(parts):
            part_clean = part.strip()
            agg_match = re.search(r'\b(MIN|MAX|COUNT|SUM|AVG|STDDEV|VARIANCE)\s*\(', part_clean, re.IGNORECASE)
            if agg_match:
                agg_map[idx] = agg_match.group(1).upper()
        return agg_map

    @staticmethod
    def _split_select_items(select_list: str) -> List[str]:
        """
        Разделяет список выборки на отдельные элементы, учитывая вложенные скобки и строки.
        """
        items = []
        current = []
        depth = 0
        in_string = False
        for ch in select_list:
            if ch == "'" and (not current or current[-1] != '\\'):
                in_string = not in_string
                current.append(ch)
            elif ch == '(' and not in_string:
                depth += 1
                current.append(ch)
            elif ch == ')' and not in_string:
                depth -= 1
                current.append(ch)
            elif ch == ',' and depth == 0 and not in_string:
                item = ''.join(current).strip()
                if item:
                    items.append(item)
                current = []
            else:
                current.append(ch)
        if current:
            item = ''.join(current).strip()
            if item:
                items.append(item)
        return items

    @staticmethod
    def _add_coalesce_defaults(stmt: str, variables: List[str], agg_functions: Dict[int, str], var_types: Dict[str, str] = None) -> str:
        """
        Модифицирует SELECT INTO statement, добавляя COALESCE для дефолтных значений.
        """
        match = re.search(r'\bSELECT\s+(.*?)\s+INTO\b', stmt, re.IGNORECASE | re.DOTALL)
        if not match:
            return stmt
        select_part = match.group(1).strip()
        # Разделяем на отдельные выражения
        select_items = ExecuteParser._split_select_items(select_part)
        # Модифицируем каждый item, добавляя COALESCE
        modified_items = []
        for idx, item in enumerate(select_items):
            item_clean = item.strip()
            if idx in agg_functions:
                agg_func = agg_functions[idx]
                var_name = variables[idx] if idx < len(variables) else None
                var_type = var_types.get(var_name, 'text') if var_name and var_types else 'text'
                default_with_type = ExecuteParser._get_default_for_agg_func_and_type(agg_func, var_type)
                modified_item = f"COALESCE({item_clean}, {default_with_type})"
            else:
                modified_item = item_clean
            modified_items.append(modified_item)
        modified_select = ', '.join(modified_items)
        before_select = stmt[:match.start()]
        after_into = stmt[match.end():]
        return f"{before_select}SELECT {modified_select} INTO{after_into}"

    @staticmethod
    def _remove_into_clause(sql: str) -> str:
        """
        Удаляет INTO ... часть из SQL запроса.
        Пример: "SELECT a, b INTO v1, v2 FROM t" -> "SELECT a, b FROM t"
        """
        match = re.search(r'\s+INTO\s+', sql, re.IGNORECASE)
        if not match:
            return sql
        before_into = sql[:match.start()]
        after_into = sql[match.end():]
        # Находим первое ключевое слово после списка переменных
        kw_match = re.search(r'\b(FROM|WHERE|GROUP|ORDER|LIMIT|RETURNING)\b', after_into, re.IGNORECASE)
        if kw_match:
            return before_into + ' ' + after_into[kw_match.start():]
        else:
            # Нет ключевого слова — значит после INTO только переменные и конец
            return before_into

    @staticmethod
    def _get_default_for_agg_func_and_type(agg_func: str, var_type: str) -> str:
        """
        Возвращает дефолт значение с правильной типизацией для функции агрегации и типа переменной.
        """
        agg_upper = agg_func.upper() if agg_func else ''
        var_type_lower = var_type.lower().strip() if var_type else 'text'
        var_type_base = re.sub(r'\(\d+\)', '', var_type_lower)
        if 'date' in var_type_base or 'timestamp' in var_type_base:
            if agg_upper == 'MIN':
                default_val = '1900-01-01'
            else:  # MAX или другие
                default_val = '2099-12-31'
            if 'timestamp' in var_type_base:
                return f"'{default_val}'::timestamp"
            else:
                return f"'{default_val}'::date"
        elif any(t in var_type_base for t in ['int', 'integer', 'bigint', 'smallint']):
            if agg_upper == 'COUNT':
                return "0"
            else:
                return "1"
        elif any(t in var_type_base for t in ['numeric', 'decimal', 'float', 'double', 'real']):
            if agg_upper in ('SUM', 'AVG'):
                return "0.0"
            else:
                return "0.0"
        elif 'uuid' in var_type_base:
            return "'00000000-0000-0000-0000-000000000000'::uuid"
        elif 'json' in var_type_base:
            cast_type = "::jsonb" if 'jsonb' in var_type_base else "::json"
            return f"'{{}}{cast_type}'"
        elif 'time' in var_type_base and 'timestamp' not in var_type_base:
            return "'00:00:00'::time"
        elif any(t in var_type_base for t in ['text', 'varchar', 'char']):
            return "''"
        else:
            return 'NULL'

    @staticmethod
    def get_default_value_for_type(var_type: str) -> str:
        """
        Возвращает значение по умолчанию для заданного типа PostgreSQL (БЕЗ типизации).
        Используется для замены сложных выражений на безопасный дефолт.
        Примеры: 'date' -> '1900-01-01', 'uuid' -> '00000000-...', 'text' -> ''
        """
        var_type_lower = var_type.lower().strip() if var_type else 'text'
        var_type_base = re.sub(r'\(\d+\)', '', var_type_lower)
        
        if 'date' in var_type_base or 'timestamp' in var_type_base:
            return '1900-01-01'
        elif any(t in var_type_base for t in ['int', 'integer', 'bigint', 'smallint']):
            return '0'
        elif any(t in var_type_base for t in ['numeric', 'decimal', 'float', 'double', 'real']):
            return '0.0'
        elif 'uuid' in var_type_base:
            return '00000000-0000-0000-0000-000000000000'
        elif 'json' in var_type_base:
            return '{}'
        elif 'time' in var_type_base and 'timestamp' not in var_type_base:
            return '00:00:00'
        elif any(t in var_type_base for t in ['text', 'varchar', 'char']):
            return ''
        else:
            return 'NULL'

    @staticmethod
    def get_default_literal_for_type(var_type: str) -> str:
        """
        Возвращает SQL-литерал по умолчанию с приведением типа для подстановки в запрос.
        Используется когда значение переменной пустое или сложное — подставляем безопасный
        литерал, чтобы не ломать синтаксис (например, не оставлять "x - " или " - ::INTERVAL").
        """
        var_type_lower = (var_type or 'text').lower().strip()
        var_type_base = re.sub(r'\(\d+\)', '', var_type_lower)
        if 'date' in var_type_base:
            return "'1900-01-01'::date"
        if 'timestamp' in var_type_base:
            return "'1900-01-01'::timestamp"
        if any(t in var_type_base for t in ['int', 'integer', 'bigint', 'smallint']):
            return '0'
        if any(t in var_type_base for t in ['numeric', 'decimal', 'float', 'double', 'real']):
            return '0.0'
        if 'interval' in var_type_base:
            return "'0 days'::interval"
        if 'uuid' in var_type_base:
            return "'00000000-0000-0000-0000-000000000000'::uuid"
        if 'json' in var_type_base:
            return "'{}'::jsonb" if 'jsonb' in var_type_base else "'{}'::json"
        if 'time' in var_type_base and 'timestamp' not in var_type_base:
            return "'00:00:00'::time"
        if any(t in var_type_base for t in ['text', 'varchar', 'char']):
            return "NULL"
        return 'NULL'