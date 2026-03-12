#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import json
import psycopg2
import hashlib
import pglast
from pglast.ast import RangeVar, TruncateStmt, InsertStmt, DeleteStmt, UpdateStmt, SelectStmt, CopyStmt
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime, timedelta
from dataclasses import dataclass

from . import block_parser
from . import plan_adjuster
from . import load_calculator
from .temp_table_tracker import TempTableTracker
from .block_parser import split_plpgsql_blocks
from .sql_object_extractor import SQLObjectExtractor
from .nested_block_extractor import extract_nested_sql_blocks, NestedBlockExtractor
from .execute_parser import ExecuteParser
from .antipattern_detector import detect_antipatterns, get_hedge_recommendations, GENERAL_HEDGE_RECOMMENDATIONS


@dataclass
class SourceStats:
    """Статистика источника данных (таблицы)"""
    name: str
    rows_estimate: int
    columns: int
    avg_row_size_bytes: float
    data_types: List[str]
    memory_estimate_gb: float
    source_type: str
    is_temp: bool = False


@dataclass
class ClusterConfig:
    """Конфигурация кластера Greenplum"""
    segments: int = 120
    ram_per_seg_gb: float = 153.6
    work_mem_overhead: float = 1.25


class DetailedGreenplumFunctionAnalyzer:
    """
    Автономный анализатор с двухэтапным процессом
    Поддерживает как функции, так и обычные SQL запросы
    """

    def __init__(self, config: Optional[ClusterConfig] = None):
        self.config = config or ClusterConfig()
        self.conn = None
        self.block_results = []
        self.discovered_tables = {}
        self.physical_tables = set()
        self.temp_tables = set()
        self.blocks = []
        self.block_types = []
        self.func_name = "unknown"
        self.function_params = []
        self.variables = {}
        self.variable_line_numbers = {}
        self.temp_table_tracker = TempTableTracker()
        self.input_type = None
        self.view_to_tables_map = {}
        self.plan_cache = {}
        self.multipliers = {
            'Seq Scan': 1.15,
            'Index Scan': 0.05,
            'Bitmap Heap Scan': 0.1,
            'Bitmap Index Scan': 0.1,
            'Nested Loop': 1.0,
            'Hash Join': 3.2,
            'Merge Join': 1.0,
            'Sort': 6.0,
            'Hash Aggregate': 5.5,
            'Group Aggregate': 5.5,
            'Unique': 10.0,
            'Gather Motion': 1.5,
            'Redistribute Motion': 1.5,
            'Broadcast Motion': 1.5,
            'ModifyTable': 1.0,
        }
        self.var_types: Dict[str, str] = {}  # имя переменной -> тип

    def reset_for_rerun(self):
        """
        Сбрасывает состояние анализатора для повторного запуска
        Очищает результаты предыдущего анализа, сохраняя discovery данные
        """
        print("🔄 Сброс состояния анализатора для повторного запуска")
        self.block_results = []
        self.variables = {}
        self.plan_cache = {}

    def connect(self, conn_string: str) -> bool:
        """Устанавливает соединение с Greenplum"""
        try:
            self.conn = psycopg2.connect(conn_string)
            self.conn.autocommit = True
            print("✅ Подключение к Greenplum установлено")
            return True
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            return False

    def _execute_query(self, query: str, params: tuple = None) -> Optional[List]:
        """Выполняет SQL-запрос и возвращает результаты"""
        if not self.conn:
            return None
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, params or ())
                return cur.fetchall()
        except Exception as e:
            print(f"⚠️ Ошибка запроса: {str(e)[:100]}")
            return None

    def _get_object_type(self, schema: str, name: str) -> Optional[str]:
        """Определяет тип объекта: 'table', 'view' или None"""
        query = """
            SELECT relkind 
            FROM pg_class c 
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = %s AND c.relname = %s
        """
        result = self._execute_query(query, (schema, name))
        if result:
            relkind = result[0][0]
            if relkind == 'r':
                return 'table'
            elif relkind == 'v':
                return 'view'
        return None

    def _get_view_definition(self, schema: str, view_name: str) -> Optional[str]:
        """Получает определение представления"""
        query = """
            SELECT pg_get_viewdef(c.oid, true)
            FROM pg_class c
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = %s AND c.relname = %s AND c.relkind = 'v'
        """
        result = self._execute_query(query, (schema, view_name))
        return result[0][0] if result and result[0] else None

    def _detect_input_type(self, sql_text: str) -> str:
        """
        Определяет тип входных данных: 'function' или 'query'
        """
        sql_upper = sql_text.strip().upper()

        # Признаки функции
        function_indicators = [
            'CREATE OR REPLACE FUNCTION',
            'CREATE FUNCTION',
            'RETURNS',
            'LANGUAGE PLPGSQL',
            'LANGUAGE SQL',
            'AS $$',
            'DECLARE'
        ]

        for indicator in function_indicators:
            if indicator in sql_upper:
                return 'function'

        return 'query'

    def _extract_function_body(self, ddl: str) -> str:
        """
        Извлекает тело функции из DDL (поддержка $tag$ и $$).
        """
        if 'FUNCTION' not in ddl.upper():
            return ddl
        # Пытаемся найти $tag$ ... $tag$
        pattern = r'AS\s*\$([^$]*)\$\s*(.*?)\s*\$\1\$'
        match = re.search(pattern, ddl, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(2).strip()
        # Пытаемся $$ ... $$
        patterns = [
            r'AS\s*\$\$\s*(.*?)\s*\$\$\s*(?:LANGUAGE|EXECUTE|VOLATILE|IMMUTABLE|STABLE|SECURITY|COST|ROWS|SET|FROM|$$|$)',
            r'AS\s*\$\$([\s\S]*?)\$\$',
        ]
        for pattern in patterns:
            body_match = re.search(pattern, ddl, re.IGNORECASE | re.DOTALL)
            if body_match:
                return body_match.group(1).strip()
        return ddl

    def _extract_objects_from_sql(self, sql: str) -> List[Tuple[str, str]]:
        """
        Извлекает объекты из SQL с использованием pglast.
        """
        return SQLObjectExtractor.extract_objects(sql)

    def _resolve_object_to_tables(self, schema: str, name: str, visited: Set = None) -> Set[Tuple[str, str]]:
        """Рекурсивно раскрывает объект до физических таблиц"""
        if visited is None:
            visited = set()

        key = f"{schema}.{name}".lower()
        if key in visited:
            return set()

        visited.add(key)

        obj_type = self._get_object_type(schema, name)

        if obj_type == 'table':
            return {(schema, name)}

        if obj_type == 'view':
            view_ddl = self._get_view_definition(schema, name)
            if view_ddl:
                objects = self._extract_objects_from_sql(view_ddl)
                tables = set()
                for s, t in objects:
                    tables.update(self._resolve_object_to_tables(s, t, visited))
                return tables

        return set()

    def _parse_function_signature(self, ddl: str) -> Tuple[str, List[str]]:
        """Извлекает имя функции и параметры из сигнатуры"""
        sig_match = re.search(r'CREATE.*?FUNCTION\s+(?:\w+\.)?(\w+)\s*\((.*?)\)', ddl, re.IGNORECASE | re.DOTALL)
        if not sig_match:
            return "unknown", []

        func_name = sig_match.group(1)
        sig = sig_match.group(2).strip()

        if not sig:
            return func_name, []

        params = []
        bracket_level = 0
        current = []

        for char in sig:
            if char == '(':
                bracket_level += 1
                current.append(char)
            elif char == ')':
                bracket_level -= 1
                current.append(char)
            elif char == ',' and bracket_level == 0:
                param = ''.join(current).strip()
                if param:
                    param_name = param.split()[0].strip()
                    params.append(param_name)
                current = []
            else:
                current.append(char)

        if current:
            param = ''.join(current).strip()
            if param:
                param_name = param.split()[0].strip()
                params.append(param_name)

        return func_name, params

    # -------------------------------------------------------------------------
    # ПАРСИНГ СЕКЦИИ DECLARE
    # -------------------------------------------------------------------------
    def _parse_declare_section(self, body: str) -> Dict[str, Tuple[str, str, int]]:
        """
        Парсит секцию DECLARE и возвращает словарь переменных:
        {имя: (тип, значение_по_умолчанию, номер_строки)}
        """
        declare_match = re.search(r'DECLARE\s+(.*?)BEGIN', body, re.IGNORECASE | re.DOTALL)
        if not declare_match:
            return {}
        declare_text = declare_match.group(1)
        declare_text = re.sub(r'--.*?$', '', declare_text, flags=re.MULTILINE)
        declare_text = re.sub(r'/\*.*?\*/', '', declare_text, flags=re.DOTALL)
        variables = {}
        pattern = re.compile(
            r'''
            \b([a-z_][a-z0-9_]*)\s+           # имя переменной
            (?:CONSTANT\s+)?                   # необязательный CONSTANT
            ([a-z_][a-z0-9_.]+(?:\[\])?)       # тип
            (?:\s+NOT\s+NULL)?                  # необязательный NOT NULL
            (?:\s*:=\s*(.*?))?                   # необязательное значение по умолчанию
            \s*;                                 # завершающая точка с запятой
            ''',
            re.IGNORECASE | re.VERBOSE | re.DOTALL
        )
        for match in pattern.finditer(declare_text):
            var_name = match.group(1)
            var_type = match.group(2).strip().lower()  # нормализуем тип
            var_value = match.group(3)
            if var_value is None:
                var_value = 'NULL'
            else:
                var_value = var_value.strip()
                var_value = self._strip_literal_quotes(var_value)
            variables[var_name] = (var_type, var_value, 0)
        return variables

    # -------------------------------------------------------------------------
    # ВСПОМОГАТЕЛЬНЫЙ МЕТОД: очищение типов кастингов из значений
    # -------------------------------------------------------------------------
    def _strip_all_castings(self, value: str) -> str:
        """
        Полностью удаляет все кастинги типов (::type) из значения.
        Используется для финального очищения переменных перед использованием в SQL.
        """
        if not value or value == 'NULL':
            return value

        value_str = str(value)

        # Удаляем ВСЕ кастинги типов - вне зависимости от того какой это тип
        # Используем цикл чтобы удалить множественные кастинги (::date::int и т.д.)
        prev = None
        while prev != value_str:
            prev = value_str
            # Удаляем ::type где type это последовательность букв и подчёркиваний
            value_str = re.sub(r'::\w+', '', value_str)

        # Убираем множественные пробелы
        value_str = ' '.join(value_str.split())

        # Удаляем оставшиеся одиночные кавычки если выражение стало пустым
        if value_str == "''":
            value_str = ""

        return value_str

    # -------------------------------------------------------------------------
    # ВСПОМОГАТЕЛЬНЫЙ МЕТОД: удаление внешних кавычек у литералов
    # -------------------------------------------------------------------------
    def _strip_literal_quotes(self, value: str) -> str:
        """
        Удаляет внешние одинарные кавычки, если это простой строковый литерал.
        """
        if value is None or value == 'NULL':
            return value
        s = value.strip()
        if s.startswith("'") and s.endswith("'"):
            # Простейшая проверка: нет ли внутри неэкранированных кавычек
            inner = s[1:-1]
            # Если внутри есть кавычка, которая не экранирована (''), то это сложный случай
            # Для простоты будем считать, что если есть кавычка, то не удаляем
            if "'" not in inner:
                return inner
        return value

    # -------------------------------------------------------------------------
    # ВСПОМОГАТЕЛЬНЫЙ МЕТОД: форматирование значения переменной для подстановки
    # -------------------------------------------------------------------------
    def _format_variable_value(self, value: str, var_name: str = None) -> str:
        """
        Возвращает строковое представление значения переменной для подстановки в SQL.
        Если известен тип переменной, добавляет приведение типа.
        Пустые или сложные значения заменяются на типобезопасный литерал (с cast),
        чтобы не ломать синтаксис в обоих типах функций (function.sql и function_1.sql).
        """
        if value is None or value == '' or value == 'NULL':
            if var_name and var_name in self.var_types:
                return ExecuteParser.get_default_literal_for_type(self.var_types[var_name])
            return 'NULL'
        if '::' in value:
            # Нормализуем литерал с приведением типа: убираем лишние кавычки (''2024-01-01'::date' → '2024-01-01'::date).
            v = value.strip()
            # Один или несколько ' в начале, содержимое до '::, тип, опционально пробелы и закрывающая кавычка.
            match = re.match(r"^'+([^']*)'::\s*(\w+)\s*'?\s*$", v)
            if match:
                return f"'{match.group(1)}'::{match.group(2)}"
            # Fallback: извлечь YYYY-MM-DD и тип после последнего ::, чтобы убрать лишние кавычки.
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', v)
            type_match = re.search(r'::\s*(\w+)\s*$', v)
            if date_match and type_match:
                return f"'{date_match.group(1)}'::{type_match.group(1)}"
            return value
        if re.match(r'^-?\d+(\.\d+)?$', value):
            return value
        if value == 'current_date':
            return 'CURRENT_DATE'
        # Простые литералы даты (только YYYY-MM-DD) не считаем сложными — иначе для function_1
        # значения v_buf_min_dt/v_buf_max_dt (1900-01-01, 2099-12-31) попадают в ветку «сложное» и ломают подстановку.
        if re.match(r'^\d{4}-\d{2}-\d{2}$', value.strip()):
            if var_name and var_name in self.var_types and 'date' in self.var_types[var_name].lower():
                return f"'{value}'::date"
            if var_name and var_name in self.var_types and 'timestamp' in self.var_types[var_name].lower():
                return f"'{value}'::timestamp"
        # Сложное выражение (операции, пробелы, кавычки, interval) — подставляем типобезопасный литерал с cast.
        if any(ch in value for ch in ['+', '-', '*', '/', '(', ')', ' ']) or "'" in value or 'interval' in value.lower():
            if var_name and var_name in self.var_types:
                return ExecuteParser.get_default_literal_for_type(self.var_types[var_name])
            return 'NULL'

        # Если известен тип переменной и это дата/время – добавляем приведение
        if var_name and var_name in self.var_types:
            var_type = self.var_types[var_name].lower()
            if 'date' in var_type:
                return f"'{value}'::date"
            if 'timestamp' in var_type:
                return f"'{value}'::timestamp"
            if 'time' in var_type and 'timestamp' not in var_type:
                return f"'{value}'::time"
        # По умолчанию – строка в кавычках
        return f"'{value}'"

    # -------------------------------------------------------------------------
    # ВСПОМОГАТЕЛЬНЫЙ МЕТОД: получение значения по умолчанию для типа
    # -------------------------------------------------------------------------
    def _get_default_value_for_type(self, var_type: str) -> str:
        """
        Возвращает значение по умолчанию для заданного типа PostgreSQL.
        Делегирует на ExecuteParser.get_default_value_for_type для консистентности.
        """
        return ExecuteParser.get_default_value_for_type(var_type)

    # -------------------------------------------------------------------------
    # ВСПОМОГАТЕЛЬНЫЙ МЕТОД: применение типизации к значению
    # -------------------------------------------------------------------------
    def _apply_type_casting(self, value: str, var_type: str) -> str:
        """
        Применяет типизацию к значению на основе типа переменной.
        Например: '1900-01-01' + 'date' -> '1900-01-01'::date
        """
        if value == 'NULL' or not value:
            return 'NULL'
        
        var_type_lower = var_type.lower().strip()
        # Удаляем размеры типов
        var_type_base = re.sub(r'\(\d+\)', '', var_type_lower)
        
        # Обворачиваем в кавычки (если еще не обвернут) и добавляем типизацию
        if not value.startswith("'"):
            value = f"'{value}'"
        
        # Добавляем типизацию
        if 'date' in var_type_base:
            return f"{value}::date"
        elif 'timestamp' in var_type_base:
            return f"{value}::timestamp"
        elif 'time' in var_type_base and 'timestamp' not in var_type_base:
            return f"{value}::time"
        elif 'uuid' in var_type_base:
            return f"{value}::uuid"
        elif 'json' in var_type_base:
            # Для JSON не добавляем типизацию если уже в кавычках
            return f"{value}::jsonb" if 'jsonb' in var_type_base else f"{value}::json"
        elif 'interval' in var_type_base:
            return f"{value}::interval"
        else:
            # Для остальных типов возвращаем как есть (число не нужно обворачивать)
            if re.match(r'^-?\d+(\.\d+)?$', value.strip("'")):
                return value.strip("'")
            return value

    # -------------------------------------------------------------------------
    # ВЫЧИСЛЕНИЕ ПРОСТЫХ ВЫРАЖЕНИЙ ЧЕРЕЗ SQL
    # -------------------------------------------------------------------------
    def _evaluate_sql_expression(self, expr: str, variables: Dict[str, str]) -> str:
        """
        Облегчённое вычисление выражения БЕЗ обращения к БД.
        Возвращает нормализованную строку после подстановки переменных и удаления кастингов.
        Это устраняет SQL-ошибки при анализе сложных PL/pgSQL выражений.
        """
        expr_with_vars = self._replace_variables_safe(expr, variables)
        expr_clean = self._strip_all_castings(expr_with_vars)
        # Исправляем возможные кавычки вокруг CURRENT_DATE
        expr_clean = re.sub(r"'CURRENT_DATE'", "CURRENT_DATE", expr_clean, flags=re.IGNORECASE)

        return expr_clean

    # -------------------------------------------------------------------------
    # ВЫЧИСЛЕНИЕ ПРОСТЫХ ВЫРАЖЕНИЙ (устаревший, оставлен для обратной совместимости)
    # -------------------------------------------------------------------------
    def _evaluate_expression(self, expr: str, variables: Dict[str, str]) -> str:
        """
        Вычисляет выражение, подставляя значения переменных.
        После подстановки удаляет все кастинги.
        """
        result = expr

        # Подставляем значения переменных (без защиты кастингов)
        sorted_vars = sorted(variables.items(), key=lambda x: (-len(x[0]), x[0]))
        for var_name, var_value in sorted_vars:
            if var_value in (None, 'NULL', ''):
                continue

            # Форматируем значение для подстановки
            formatted_value = self._format_variable_value(var_value)
            pattern = r'\b' + re.escape(var_name) + r'\b'
            result = re.sub(pattern, formatted_value, result)

        # Удаляем все кастинги типов
        result = self._strip_all_castings(result)

        # Защита: если после подстановки остались "подозрительные" идентификаторы, не трогаем дальше
        idents = re.findall(r'\b([a-z_][a-z0-9_]*)\b', result, flags=re.IGNORECASE)
        postgres_keywords = {
            'date', 'interval', 'extract', 'now', 'current_date', 'cast',
            'and', 'or', 'not', 'null', 'case', 'when', 'then', 'else', 'end',
            'greatest', 'least'
        }
        for ident in idents:
            lname = ident.lower()
            if lname in postgres_keywords:
                continue
            if lname not in {v.lower() for v in variables.keys()}:
                return expr  # возвращаем исходное выражение, чтобы не порождать некорректный SQL

        return result

    def _is_expression(self, value: str) -> bool:
        """Определяет, является ли значение выражением"""
        if not value or value == 'NULL' or value == '':
            return False
        if value.startswith("'") and value.endswith("'"):
            return False
        if re.match(r'^-?\d+(\.\d+)?$', value):
            return False
        if re.match(r'^\d{4}-\d{2}-\d{2}$', value):
            return False
        indicators = [
            'date_trunc', 'interval', 'current_date', 'now()',
            '+', '-', '*', '/', '(', ')', '::', 'cast('
        ]
        return any(indicator in value.lower() for indicator in indicators)

    # -------------------------------------------------------------------------
    # БЕЗОПАСНАЯ ПОДСТАНОВКА ПЕРЕМЕННЫХ В SQL
    # -------------------------------------------------------------------------
    def _replace_variables_safe(self, sql: str, variables: Dict[str, str]) -> str:
        """
        Заменяет переменные на значения в SQL с защитой кастингов ::type.
        После замены исправляет возможные кавычки вокруг CURRENT_DATE.
        
        ВАЖНО: не подставляет значения в targets `SELECT ... INTO ...` (PL/pgSQL),
        иначе INTO-часть превращается в литералы и ломает парсинг/EXPLAIN.
        """
        result = sql

        # 0. Защищаем targets в SELECT/WITH ... INTO ... (чтобы не заменить имена переменных значениями)
        into_placeholders: Dict[str, str] = {}
        into_counter = 0

        if re.match(r'^\s*(SELECT|WITH)\b', result, flags=re.IGNORECASE) and re.search(r'\bINTO\b', result, flags=re.IGNORECASE):
            def _protect_into_targets(match: re.Match) -> str:
                nonlocal into_counter
                placeholder = f"__INTO_TARGETS_PROTECT_{into_counter}__"
                into_placeholders[placeholder] = match.group('targets')
                into_counter += 1
                strict_part = match.group('strict') or ''
                # сохраняем INTO и STRICT (если есть), targets заменяем плейсхолдером
                return f"INTO{strict_part} {placeholder}"

            result = re.sub(
                r'(?is)\bINTO\b(?P<strict>\s+STRICT)?\s+(?P<targets>.*?)(?=(\s+\bFROM\b|\s+\bWHERE\b|\s+\bGROUP\b|\s+\bHAVING\b|\s+\bORDER\b|\s+\bLIMIT\b|\s+\bOFFSET\b|\s+\bRETURNING\b|;|$))',
                _protect_into_targets,
                result,
            )
        
        # 1. Защищаем все кастинги ::type
        cast_placeholders = {}
        cast_counter = 0
        for match in re.finditer(r'::[a-zA-Z_][a-zA-Z0-9_]*', result):
            placeholder = f"__CAST_PROTECT_{cast_counter}__"
            cast_placeholders[placeholder] = match.group(0)
            result = result.replace(match.group(0), placeholder, 1)
            cast_counter += 1

        # 2. Заменяем переменные (никогда не пропускаем: пустые/unknown → типобезопасный дефолт или NULL,
        # иначе в SQL остаются обрывки вроде "v_date_from - " или " - ::INTERVAL" и ломается парсинг).
        sorted_vars = sorted(variables.items(), key=lambda x: (-len(x[0]), x[0]))
        for var_name, var_value in sorted_vars:
            if var_value is None or var_value == '':
                cleaned_value = ''
                unquoted = ''
            else:
                raw = str(var_value).strip()
                # Нормализуем вид '...'::type до одного слоя кавычек до strip, иначе в подстановку попадает ''...'::date'.
                if '::' in raw and re.search(r'\d{4}-\d{2}-\d{2}', raw):
                    dm = re.search(r'(\d{4}-\d{2}-\d{2})', raw)
                    tm = re.search(r'::\s*(\w+)\s*$', raw)
                    if dm and tm:
                        raw = f"'{dm.group(1)}'::{tm.group(1)}"
                cleaned_value = self._strip_all_castings(raw)
                unquoted = self._strip_literal_quotes(cleaned_value)
            replacement = self._format_variable_value(unquoted, var_name)
            pattern = r'\b' + re.escape(var_name) + r'\b'
            result = re.sub(pattern, replacement, result)

        # 3. Восстанавливаем кастинги
        for placeholder, original_cast in cast_placeholders.items():
            result = result.replace(placeholder, original_cast)

        # 3.1 Восстанавливаем INTO targets
        for placeholder, original_targets in into_placeholders.items():
            result = result.replace(placeholder, original_targets)

        # 4. Финальное исправление: убираем кавычки вокруг CURRENT_DATE
        result = re.sub(r"'CURRENT_DATE'", "CURRENT_DATE", result, flags=re.IGNORECASE)

        # 5. Убираем лишний слой кавычек у литералов даты (''2024-01-01'::date' → '2024-01-01'::date)
        result = re.sub(r"''(\d{4}-\d{2}-\d{2})'::(\w+)'", r"'\1'::\2", result)

        return result

    # -------------------------------------------------------------------------
    # ОБРАБОТКА EXECUTE
    # -------------------------------------------------------------------------
    def _process_execute_block(self, block: str, variables: Dict[str, str]) -> Optional[str]:
        """
        Пытается извлечь и выполнить подстановку для EXECUTE ... format(...) или EXECUTE ... USING ...
        Возвращает итоговый SQL или None, если не удалось разобрать.
        """
        return ExecuteParser.parse(block, variables)

    # -------------------------------------------------------------------------
    # ВЫПОЛНЕНИЕ SELECT INTO ДЛЯ РАСЧЁТА ПЕРЕМЕННЫХ
    # -------------------------------------------------------------------------
    def _execute_select_into(self, stmt: str, variables: Dict[str, str]) -> Dict[str, str]:
        """
        Выполняет SELECT INTO запрос и возвращает словарь {имя_переменной: значение}.
        SELECT использует COALESCE чтобы всегда возвращать данные (с дефолтами если нет результатов).
        """
        print(f"      [DEBUG] _execute_select_into: processing SELECT INTO statement")
        stmt = stmt.rstrip(';').strip()
        
        # Проверка: в блоке ДОЛЖЕН быть SELECT и INTO для обработки
        if 'SELECT' not in stmt.upper() or 'INTO' not in stmt.upper():
            print(f"      [DEBUG] Not a SELECT INTO statement, skipping")
            return {}
        
        print(f"      [DEBUG] Calling ExecuteParser.parse_select_into...")
        # Парсим SELECT INTO с помощью ExecuteParser (с добавлением COALESCE)
        # Передаем информацию о типах переменных для правильной типизации дефолтов
        parse_result = ExecuteParser.parse_select_into(stmt, variables, self.var_types)
        if not parse_result or 'variables' not in parse_result:
            print(f"      [DEBUG] No variables found in INTO clause")
            return {}
        
        into_vars = parse_result['variables']
        agg_functions = parse_result.get('agg_functions', {})
        
        print(f"      [DEBUG] into_vars: {into_vars}")
        print(f"      [DEBUG] agg_functions: {agg_functions}")
        
        # Вместо реального выполнения SQL используем дефолтные значения
        # на основе функции агрегации и типа переменной.
        res: Dict[str, str] = {}
        for idx, var in enumerate(into_vars):
            agg_func = agg_functions.get(idx)
            var_type = self.var_types.get(var, 'text')
            if agg_func:
                default_with_type = ExecuteParser._get_default_for_agg_func_and_type(agg_func, var_type)
                cleaned = self._strip_all_castings(default_with_type)
                cleaned = self._strip_literal_quotes(cleaned)
                res[var] = cleaned
                print(f"      [DEBUG] var {var} = {cleaned} (default for {agg_func})")
            else:
                res[var] = 'NULL'
                print(f"      [DEBUG] var {var} = NULL (no agg function)")
        
        return res


    # -------------------------------------------------------------------------
    # ПОСЛЕДОВАТЕЛЬНАЯ ОБРАБОТКА ПЕРЕМЕННЫХ
    # -------------------------------------------------------------------------
    def _process_variables_sequentially(self, body: str, param_values: Dict[str, str]) -> Dict[str, str]:
        """
        Последовательно обрабатывает операторы функции для вычисления переменных.
        Правильно обрабатывает зависимости между переменными, включая выражения с датами.
        """
        print("\n📋 [DEBUG] Начало обработки переменных")
        print(f"[DEBUG] Параметры: {param_values}")

        # ОГРОМНЫЙ список типов PostgreSQL/Greenplum - МЫ НИКОГДА не подменяем их как переменные
        postgres_types = {
            'date', 'int', 'bigint', 'integer', 'text', 'varchar', 'numeric', 
            'boolean', 'timestamp', 'interval', 'uuid', 'json', 'jsonb',
            'smallint', 'float', 'double', 'real', 'decimal', 'char', 'bytea',
            'oid', 'name', 'regclass', 'record', 'anyarray', 'anyelement',
            'time', 'timetz', 'timestamptz', 'box', 'point', 'polygon', 'circle',
            'line', 'lseg', 'path', 'inet', 'cidr', 'macaddr', 'bit', 'varbit',
            'tsrange', 'tstzrange', 'daterange', 'int4range', 'int8range', 'numrange',
            'hstore', 'xml', 'money', 'pg_lsn', 'tsvector', 'tsquery'
        }

        # Получаем начальные значения из DECLARE
        declare_vars = self._parse_declare_section(body)
        variables = {}
        variable_expressions = {}  # Отслеживаем исходные выражения
        self.var_types = {}  # очищаем перед новым запуском

        # Добавляем переменные из DECLARE (пропускаем те, которые названы в честь типов PostgreSQL)
        for name, (var_type, value, line) in declare_vars.items():
            if name.lower() not in postgres_types:
                self.var_types[name] = var_type
                variables[name] = value
                variable_expressions[name] = value
                print(f"  [DECLARE] {name} ({var_type}) = {value}")
            else:
                print(f"  [DECLARE] {name} = {value} (⚠️  ПРОПУЩЕНА - это тип PostgreSQL, не переменная!)")

        # Добавляем параметры
        for param_name, param_value in param_values.items():
            if param_name.lower() not in postgres_types:
                variables[param_name] = param_value
                variable_expressions[param_name] = param_value
                print(f"  [PARAM] {param_name} = {param_value}")
            else:
                print(f"  [PARAM] {param_name} = {param_value} (⚠️  ПРОПУЩЕН - это тип PostgreSQL!)")

        statements = self.blocks
        
        # 🔧 Разбиваем каждый блок на отдельные statements по точкам с запятой
        # Это необходимо для выделения SELECT INTO и других отдельных операторов
        expanded_statements = []
        for block in statements:
            # Разбиваем по точкам с запятой, но сохраняем точку с запятой
            parts = block.split(';')
            for part in parts:
                part = part.strip()
                if part:
                    expanded_statements.append(part + ';')
        
        statements = expanded_statements
        print(f"\n[DEBUG] Найдено {len(statements)} операторов для выполнения (после разбиения по ;)")

        # Предварительный проход: обработка значений переменных DECLARE,
        # которые могли содержать кастинги типов и ссылки на параметры
        print(f"\n[DEBUG] Предварительная обработка DECLARE переменных:")
        for var_name in list(variables.keys()):
            var_value = variables[var_name]
            if '::' in str(var_value):
                computed = self._evaluate_expression(str(var_value), param_values)
                cleaned = self._strip_all_castings(computed)
                cleaned = self._strip_literal_quotes(cleaned)
                if cleaned != var_value:
                    print(f"  {var_name}: {var_value} → {cleaned}")
                    variables[var_name] = cleaned

        # Множественные проходы для учёта зависимостей
        max_passes = 10
        for pass_num in range(max_passes):
            changed = False
            print(f"\n[DEBUG] Проход {pass_num + 1}:")

            for i, stmt in enumerate(statements):
                stmt = stmt.strip()
                if not stmt:
                    continue

                # ⭐ Обработка SELECT INTO должна быть самой первой, чтобы переменные получили значения
                # Но ТОЛЬКО если это чистое SELECT INTO, а не SELECT внутри INSERT/WITH/других конструкций
                stmt_upper = stmt.upper()
                has_select = stmt_upper.startswith('SELECT')
                has_into = 'INTO' in stmt_upper
                has_insert = 'INSERT ' in stmt_upper
                has_with = 'WITH ' in stmt_upper
                has_create = 'CREATE ' in stmt_upper
                
                if has_select and has_into and not has_insert and not has_with and not has_create:
                    if pass_num == 0:  # логируем только в первом проходе
                        print(f"      [DEBUG] Found SELECT INTO: {stmt[:60]}...")
                    result_values = self._execute_select_into(stmt, variables)
                    if result_values:
                        for var_name, value in result_values.items():
                            # Добавляем переменные из SELECT INTO даже если их не было в DECLARE
                            # (в агентском режиме блоки могут не включать секцию DECLARE)
                            variables[var_name] = value
                            variable_expressions[var_name] = value
                            changed = True
                            print(f"    📍 {var_name} = {value} (из SELECT INTO)")
                    continue  # переходим к следующему оператору

                # Пропускаем чистые SQL запросы, кроме SELECT INTO (уже обработано выше)
                if SQLObjectExtractor.is_dml_statement(stmt):
                    continue

                # Пропускаем END;
                if re.match(r'^\s*END\s*;', stmt, re.IGNORECASE):
                    continue

                # Обработка присваиваний
                if ':=' in stmt:
                    assign_pattern = r'([a-z_][a-z0-9_]*)\s*:=\s*(.*?);'
                    matches = re.findall(assign_pattern, stmt, re.IGNORECASE | re.DOTALL)
                    for var_name, expr in matches:
                        # Проверка: переменная должна быть объявлена
                        if var_name not in variables:
                            continue

                        expr = ' '.join(expr.split())

                        # DEBUG: показываем исходное выражение
                        if expr != 'NULL' and expr not in [str(variables.get(v, '')) for v in variables]:
                            print(f"      [DEBUG EXPR] {var_name} := {expr[:60]}")

                        has_variables = any(re.search(r'\b' + re.escape(vname) + r'\b', expr) 
                                            for vname in variables if vname != var_name)
                        has_casting = '::' in expr

                        if has_variables or has_casting:
                            # ⭐ Улучшение: если выражение содержит операции с датами, вычисляем через SQL
                            if any(word in expr.lower() for word in ['date_trunc', 'interval', '+', '-', '*', '/']):
                                computed_expr = self._evaluate_sql_expression(expr, variables)
                            else:
                                computed_expr = self._evaluate_expression(expr, variables)
                        else:
                            computed_expr = expr

                        # Проверяем, остались ли неизвестные переменные
                        remaining_vars = re.findall(r'\b[a-z_][a-z0-9_]*\b', computed_expr)
                        unknown_exists = False
                        for v in remaining_vars:
                            if v != var_name and v not in variables:
                                if v.lower() not in ['date', 'interval', 'cast', 'extract', 'now', 'datenow']:
                                    unknown_exists = True
                                    break

                        if not unknown_exists:
                            if var_name not in variables or variables[var_name] != computed_expr:
                                # Очищаем кастинги и внешние кавычки
                                cleaned_expr = self._strip_all_castings(computed_expr)
                                cleaned_expr = self._strip_literal_quotes(cleaned_expr)

                                if cleaned_expr != computed_expr:
                                    print(f"      🧹 Очищено: {computed_expr[:50]} → {cleaned_expr[:50]}")

                                variables[var_name] = cleaned_expr
                                variable_expressions[var_name] = expr
                                changed = True
                                expr_preview = cleaned_expr[:50] if cleaned_expr else 'NULL'
                                print(f"    ⚡ {var_name} = {expr_preview}...")
                    continue

                # Обработка GET DIAGNOSTICS
                if stmt.upper().startswith('GET DIAGNOSTICS'):
                    get_pattern = r'GET\s+DIAGNOSTICS\s+([a-z_][a-z0-9_]*)\s*=\s*ROW_COUNT'
                    get_match = re.search(get_pattern, stmt, re.IGNORECASE)
                    if get_match:
                        var_name = get_match.group(1)
                        if var_name in variables:
                            if variables[var_name] != '0':
                                variables[var_name] = '0'
                                variable_expressions[var_name] = '0'
                                changed = True
                                print(f"    📊 GET DIAGNOSTICS {var_name} = 0")
                    continue

                # Упрощённая обработка IF, LOOP и т.п.
                if any(stmt.upper().startswith(kw) for kw in ['IF', 'LOOP', 'WHILE', 'FOR', 'CASE']):
                    if ':=' in stmt:
                        assign_pattern = r'([a-z_][a-z0-9_]*)\s*:=\s*(.*?);'
                        matches = re.findall(assign_pattern, stmt, re.IGNORECASE | re.DOTALL)
                        for var_name, expr in matches:
                            if var_name not in variables:
                                continue
                            expr = ' '.join(expr.split())
                            computed_expr = self._evaluate_expression(expr, variables)
                            remaining_vars = re.findall(r'\b[a-z_][a-z0-9_]*\b', computed_expr)
                            unknown_exists = any(v != var_name and v not in variables and v.lower() not in 
                                                ['date', 'interval', 'cast', 'extract', 'now', 'datenow'] 
                                                for v in remaining_vars)
                            if not unknown_exists:
                                if var_name not in variables or variables[var_name] != computed_expr:
                                    cleaned_expr = self._strip_all_castings(computed_expr)
                                    cleaned_expr = self._strip_literal_quotes(cleaned_expr)
                                    variables[var_name] = cleaned_expr
                                    variable_expressions[var_name] = expr
                                    changed = True
                                    expr_preview = cleaned_expr[:50] if cleaned_expr else 'NULL'
                                    print(f"    ⚡ {var_name} = {expr_preview}...")
                    continue

            if not changed:
                print(f"    Нет изменений, останов на проходе {pass_num + 1}")
                break

        print("\n[DEBUG] Все переменные после обработки:")
        for var, val in sorted(variables.items()):
            if val is None or val == 'NULL':
                print(f"  {var} = NULL")
            elif len(str(val)) > 100:
                print(f"  {var} = {str(val)[:100]}...")
            else:
                print(f"  {var} = {val}")

        return variables


    # -------------------------------------------------------------------------
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ДЛЯ GET DIAGNOSTICS
    # -------------------------------------------------------------------------
    def _process_get_diagnostics_with_rowcount(self, stmt: str, variables: Dict[str, str], rowcount: int) -> bool:
        """Обрабатывает GET DIAGNOSTICS, присваивая переменной реальное количество строк."""
        changed = False
        pattern = r'GET\s+DIAGNOSTICS\s+([a-z_][a-z0-9_]*)\s*=\s*ROW_COUNT'
        match = re.search(pattern, stmt, re.IGNORECASE)
        if match:
            var_name = match.group(1)
            # ПРОВЕРКА: переменная должна быть объявлена
            if var_name in variables:
                str_rowcount = str(rowcount)
                if variables[var_name] != str_rowcount:
                    variables[var_name] = str_rowcount
                    changed = True
                    print(f"    📊 GET DIAGNOSTICS {var_name} = {rowcount}")
        return changed

    # -------------------------------------------------------------------------
    # ОСНОВНЫЕ МЕТОДЫ DISCOVER_TABLES
    # -------------------------------------------------------------------------
    def discover_tables(self, sql_text: str, user_params: List[str] = None) -> Dict[str, Any]:
        """
        Первый этап: обнаружение таблиц в DDL или SQL запросе
        """
        self.discovered_tables = {}
        self.physical_tables = set()
        self.view_to_tables_map = {}
        self.temp_tables = set()
        self.variables = {}
        self.block_types = []
        self.temp_table_tracker = TempTableTracker()

        self.input_type = self._detect_input_type(sql_text)
        print(f"🔍 Обнаружен тип входных данных: {self.input_type}")

        if self.input_type == 'function':
            return self._discover_tables_from_function(sql_text, user_params)
        else:
            return self._discover_tables_from_query(sql_text, user_params)

    def _discover_tables_from_function(self, ddl: str, user_params: List[str] = None) -> Dict[str, Any]:
        """Обнаружение таблиц из функции с использованием pglast"""
        print("🔍 Этап 1: Обнаружение таблиц в DDL функции")
        print("   Поиск блоков и извлечение объектов: логика (парсер pglast/block_parser)")

        function_body = self._extract_function_body(ddl)
        print(f"📄 Извлечено тело функции, длина: {len(function_body)} символов")

        # Находим временные таблицы
        self.temp_tables = block_parser.extract_temp_tables_from_ddl(function_body)
        if self.temp_tables:
            print(f"📋 Найдены временные таблицы: {', '.join(self.temp_tables)}")

        # Парсим сигнатуру и параметры
        self.func_name, self.function_params = self._parse_function_signature(ddl)
        print(f"📋 Функция: {self.func_name}")
        if self.function_params:
            print(f"📋 Параметры функции: {', '.join(self.function_params)}")

        param_values = {}
        if user_params and self.function_params:
            for i, param_name in enumerate(self.function_params):
                if i < len(user_params):
                    clean_val = user_params[i].strip().strip("'").strip('"')
                    if clean_val.lower() == 'current_date':
                        param_values[param_name] = 'current_date'
                    else:
                        param_values[param_name] = clean_val
            print(f"📋 Значения параметров: {param_values}")

        # Разбиваем тело на блоки (используем обновлённую функцию split_plpgsql_blocks)
        self.blocks = split_plpgsql_blocks(function_body)
        self.block_types = [block_parser.classify_block(block) for block in self.blocks]

        print(f"🧩 [Логика] Найдено {len(self.blocks)} логических блоков в теле функции:")
        type_stats = {}
        for bt in self.block_types:
            type_stats[bt] = type_stats.get(bt, 0) + 1
        for bt, cnt in sorted(type_stats.items()):
            print(f"  • {bt}: {cnt}")

        # Вычисляем переменные
        if function_body:
            self.variables = self._process_variables_sequentially(function_body, param_values)
            print(f"📊 Вычислено {len(self.variables)} переменных")

        # Собираем таблицы
        view_definitions: Dict[Tuple[str, str], str] = {}
        all_objects: Set[Tuple[str, str]] = set()

        for i, block in enumerate(self.blocks):
            block_type = self.block_types[i]

            if not block_parser.is_executable_sql(block_type):
                continue

            # Используем безопасную замену переменных
            block_with_vars = self._replace_variables_safe(block, self.variables)

            # Минимальная очистка — только комментарии
            clean_sql = re.sub(r'--.*?$', '', block_with_vars, flags=re.MULTILINE)
            clean_sql = re.sub(r'/\*.*?\*/', '', clean_sql, flags=re.DOTALL | re.MULTILINE)

            print(f"  [DEBUG Блок {i+1} | {block_type}] длина после замены: {len(clean_sql)}")
            if len(clean_sql) > 300:
                preview = ' '.join(clean_sql[:300].splitlines())
                print(f"    Preview (первые 300): {preview} ...")

            # Используем pglast для извлечения объектов
            objects = SQLObjectExtractor.extract_objects(clean_sql)
            for sch, tbl in objects:
                all_objects.add((sch.lower(), tbl.lower()))

            print(f"  [Блок {i+1}] Найдено {len(objects)} объектов: {objects[:5]}...")

        print(f"📋 [Логика] Итого найдено {len(all_objects)} уникальных объектов из всех исполняемых блоков")

        if not self.conn:
            print("❌ Нет подключения к БД. Невозможно раскрыть представления.")
            return {
                'input_type': 'function',
                'function': self.func_name,
                'blocks_count': len(self.blocks),
                'block_types': self.block_types,
                'temp_tables': list(self.temp_tables),
                'discovered_tables': {},
                'objects_referenced_in_blocks': len(all_objects),
                'variables': self.variables,
                'status': 'error',
                'error': 'Нет подключения к БД'
            }

        # Получаем определения представлений
        if self.conn:
            for schema, name in all_objects:
                obj_type = self._get_object_type(schema, name)
                if obj_type == 'view':
                    view_def = self._get_view_definition(schema, name)
                    if view_def:
                        view_definitions[(schema.lower(), name.lower())] = view_def

        # Рекурсивно раскрываем представления
        if all_objects:
            print("\n🔍 Рекурсивное раскрытие объектов:")
            for schema, name in all_objects:
                view_key = f"{schema}.{name}"
                print(f"  📌 {view_key}")

                tables = self._resolve_object_to_tables(schema, name)
                self.physical_tables.update(tables)

                physical_table_keys = [f"{s}.{t}" for s, t in tables]
                self.view_to_tables_map[view_key] = physical_table_keys

                for s, t in tables:
                    print(f"    └─ {s}.{t}")

        print(f"\n📊 Найдено {len(self.physical_tables)} физических таблиц")

        # Отслеживаем создание временных таблиц
        for i, block in enumerate(self.blocks):
            block_type = self.block_types[i]

            temp_info = self.temp_table_tracker.extract_temp_table_from_sql(block)
            if temp_info:
                temp_name, query_type = temp_info
                self.temp_table_tracker.register_temp_table(
                    block, temp_name,
                    self.physical_tables,
                    set(view_definitions.keys()),
                    view_definitions
                )

        # Получаем статистику
        if self.physical_tables:
            print("\n📊 Сбор статистики для физических таблиц:")
            for schema, table in sorted(self.physical_tables):
                key = f"{schema}.{table}"
                stats = self._get_real_table_stats(schema, table)
                if stats:
                    self.discovered_tables[key] = {
                        'schema': schema,
                        'table': table,
                        'current_rows': stats.rows_estimate,
                        'size_gb': stats.memory_estimate_gb,
                        'avg_row_size_bytes': stats.avg_row_size_bytes,
                        'columns': stats.columns,
                        'user_rows': stats.rows_estimate
                    }
                    print(f"  📈 {key}: {stats.rows_estimate:,} строк, {stats.memory_estimate_gb:.3f} GB")
                else:
                    self.discovered_tables[key] = {
                        'schema': schema,
                        'table': table,
                        'current_rows': 0,
                        'size_gb': 0,
                        'avg_row_size_bytes': 0,
                        'columns': 0,
                        'user_rows': 0
                    }
                    print(f"  ⚠️ {key}: статистика недоступна")

        return {
            'input_type': 'function',
            'function': self.func_name,
            'blocks_count': len(self.blocks),
            'block_types': self.block_types,
            'temp_tables': list(self.temp_tables),
            'discovered_tables': self.discovered_tables,
            'view_to_tables_map': self.view_to_tables_map,
            'physical_tables_count': len(self.physical_tables),
            'objects_referenced_in_blocks': len(all_objects),
            'variables': self.variables,
            'status': 'tables_discovered'
        }

    def _discover_tables_from_query(self, query: str, user_params: List[str] = None) -> Dict[str, Any]:
        """Обнаружение таблиц в обычном SQL запросе"""
        print("🔍 Этап 1: Обнаружение таблиц в SQL запросе")
        print("   Поиск блоков и извлечение объектов: логика (парсер)")

        # Очищаем запрос от параметров если они есть
        clean_query = query
        if user_params:
            for i, param in enumerate(user_params, 1):
                placeholder = f"${i}"
                if param.startswith("'") and param.endswith("'"):
                    clean_query = clean_query.replace(placeholder, param)
                else:
                    clean_query = clean_query.replace(placeholder, f"'{param}'")

        self.blocks = block_parser.split_sql_blocks(clean_query)
        self.block_types = [block_parser.classify_block(block) for block in self.blocks]

        print(f"🧩 [Логика] Найдено {len(self.blocks)} логических блоков в запросе")

        all_objects = set()
        view_definitions = {}

        for i, block in enumerate(self.blocks):
            objects = SQLObjectExtractor.extract_objects(block)
            for sch, tbl in objects:
                all_objects.add((sch, tbl))

        print(f"📋 [Логика] Найдено {len(all_objects)} объектов (таблиц/представлений) в запросе")

        if not self.conn:
            print("❌ Нет подключения к БД. Невозможно раскрыть представления.")
            return {
                'input_type': 'query',
                'blocks_count': len(self.blocks),
                'block_types': self.block_types,
                'discovered_tables': {},
                'status': 'error',
                'error': 'Нет подключения к БД'
            }

        if self.conn:
            for schema, name in all_objects:
                obj_type = self._get_object_type(schema, name)
                if obj_type == 'view':
                    view_def = self._get_view_definition(schema, name)
                    if view_def:
                        view_definitions[(schema.lower(), name.lower())] = view_def

        if all_objects:
            print("\n🔍 Рекурсивное раскрытие объектов:")
            for schema, name in all_objects:
                view_key = f"{schema}.{name}"
                print(f"  📌 {view_key}")

                tables = self._resolve_object_to_tables(schema, name)
                self.physical_tables.update(tables)

                physical_table_keys = [f"{s}.{t}" for s, t in tables]
                self.view_to_tables_map[view_key] = physical_table_keys

                for s, t in tables:
                    print(f"    └─ {s}.{t}")

        print(f"\n📊 Найдено {len(self.physical_tables)} физических таблиц")

        if self.physical_tables:
            print("\n📊 Сбор статистики для физических таблиц:")
            for schema, table in sorted(self.physical_tables):
                key = f"{schema}.{table}"
                stats = self._get_real_table_stats(schema, table)
                if stats:
                    self.discovered_tables[key] = {
                        'schema': schema,
                        'table': table,
                        'current_rows': stats.rows_estimate,
                        'size_gb': stats.memory_estimate_gb,
                        'avg_row_size_bytes': stats.avg_row_size_bytes,
                        'columns': stats.columns,
                        'user_rows': stats.rows_estimate
                    }
                    print(f"  📈 {key}: {stats.rows_estimate:,} строк, {stats.memory_estimate_gb:.3f} GB")
                else:
                    self.discovered_tables[key] = {
                        'schema': schema,
                        'table': table,
                        'current_rows': 0,
                        'size_gb': 0,
                        'avg_row_size_bytes': 0,
                        'columns': 0,
                        'user_rows': 0
                    }
                    print(f"  ⚠️ {key}: статистика недоступна")

        return {
            'input_type': 'query',
            'blocks_count': len(self.blocks),
            'block_types': self.block_types,
            'discovered_tables': self.discovered_tables,
            'view_to_tables_map': self.view_to_tables_map,
            'physical_tables_count': len(self.physical_tables),
            'status': 'tables_discovered'
        }

    def _get_real_table_stats(self, schema: str, table_name: str) -> Optional[SourceStats]:
        """Получает реальную статистику таблицы из БД"""
        if not self.conn:
            return None

        rel_q = """
            SELECT COALESCE(reltuples::bigint, 0)
            FROM pg_class c 
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = %s AND c.relname = %s
        """
        rel_r = self._execute_query(rel_q, (schema, table_name))
        if not rel_r:
            return None

        row_count = int(rel_r[0][0]) if rel_r and rel_r[0] else 0

        col_q = """
            SELECT 
                COUNT(*) as column_count,
                AVG(CASE 
                    WHEN data_type IN ('character varying', 'text') THEN 128
                    WHEN data_type IN ('bigint', 'integer', 'smallint') THEN 8
                    WHEN data_type IN ('numeric', 'decimal') THEN 16
                    WHEN data_type IN ('date', 'timestamp', 'timestamptz') THEN 8
                    WHEN data_type IN ('boolean') THEN 1
                    WHEN data_type IN ('real', 'double precision') THEN 8
                    ELSE 32
                END)::float8 as avg_width
            FROM information_schema.columns 
            WHERE table_schema = %s AND table_name = %s
        """
        col_r = self._execute_query(col_q, (schema, table_name.lower()))

        if not col_r:
            return None

        col_count, avg_col = col_r[0]

        if col_count == 0:
            return SourceStats(
                name=f"{schema}.{table_name}",
                rows_estimate=row_count,
                columns=0,
                avg_row_size_bytes=0,
                data_types=[],
                memory_estimate_gb=0,
                source_type='table'
            )

        avg_row = float(avg_col or 32) * col_count * 1.4
        mem_gb = (avg_row * row_count * 1.25) / (1024**3) / self.config.segments

        return SourceStats(
            name=f"{schema}.{table_name}",
            rows_estimate=row_count,
            columns=int(col_count),
            avg_row_size_bytes=round(avg_row, 1),
            data_types=[],
            memory_estimate_gb=round(mem_gb, 3),
            source_type='table'
        )

    # -------------------------------------------------------------------------
    # МЕТОДЫ ДЛЯ ОЧИСТКИ SQL
    # -------------------------------------------------------------------------
    def _clean_sql_for_explain(self, sql: str) -> str:
        """Очистка SQL от PL/pgSQL конструкций и комментариев для EXPLAIN"""
        sql = sql.strip()
        # Удаляем комментарии
        sql = re.sub(r'--.*?$', '', sql, flags=re.MULTILINE)
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        sql = re.sub(r'^\s*PERFORM\s+', 'SELECT ', sql, flags=re.IGNORECASE)

        # Удаляем INTO targets только для SELECT/WITH (PL/pgSQL SELECT INTO ...).
        # Делаем это до подстановки переменных и устойчиво к любым символам в targets.
        if re.match(r'^\s*(SELECT|WITH)\b', sql, flags=re.IGNORECASE):
            sql = re.sub(
                r'(?is)\s+\bINTO\b(\s+STRICT)?\s+.*?(?=(\s+\bFROM\b|\s+\bWHERE\b|\s+\bGROUP\b|\s+\bHAVING\b|\s+\bORDER\b|\s+\bLIMIT\b|\s+\bOFFSET\b|\s+\bRETURNING\b|;|$))',
                '',
                sql,
            )

        # Если после очистки остались PL/pgSQL конструкции, заменяем на заглушку
        if sql.upper().startswith(('RETURN', 'GET DIAGNOSTICS', 'BEGIN', 'END', 'IF', 'LOOP')):
            return 'SELECT 1;'
        return sql

    def _replace_variables(self, sql: str, variables: Dict[str, str]) -> str:
        """Заменяет переменные на значения в SQL с учётом контекста (устаревший, используйте _replace_variables_safe)"""
        # Для обратной совместимости используем безопасную версию
        return self._replace_variables_safe(sql, variables)

    # -------------------------------------------------------------------------
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ДЛЯ ИЗВЛЕЧЕНИЯ ПРИСВАИВАНИЙ
    # -------------------------------------------------------------------------
    def _extract_assignments_from_block_recursive(self, block: str) -> Dict[str, str]:
        """
        Рекурсивно извлекает все присваивания := из блока и всех вложенных блоков
        """
        assignments = {}

        block = re.sub(r'EXCEPTION.*?END;', '', block, flags=re.IGNORECASE | re.DOTALL)

        def extract_from_text(text: str) -> Dict[str, str]:
            result = {}

            assign_pattern = r'([a-z_][a-z0-9_]*)\s*:=\s*(.*?);'
            matches = re.findall(assign_pattern, text, re.IGNORECASE | re.DOTALL)

            for var_name, expr in matches:
                expr = ' '.join(expr.split())
                result[var_name] = expr

            nested_pattern = r'BEGIN\s+(.*?)\s+END;'
            nested_blocks = re.findall(nested_pattern, text, re.IGNORECASE | re.DOTALL)

            for nested_block in nested_blocks:
                nested_result = extract_from_text(nested_block)
                result.update(nested_result)

            return result

        assignments = extract_from_text(block)
        return assignments

    def _extract_select_into_from_block(self, block: str) -> List[str]:
        """
        Извлекает переменные из SELECT INTO во всех вложенных блоках
        """
        variables = []

        block = re.sub(r'EXCEPTION.*?END;', '', block, flags=re.IGNORECASE | re.DOTALL)

        def extract_from_text(text: str) -> List[str]:
            result = []

            pattern = r'SELECT\s+.*?\s+INTO\s+([\w\s_,]+?)\s+FROM'
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)

            for into_clause in matches:
                vars_list = [v.strip() for v in into_clause.split(',')]
                result.extend(vars_list)

            nested_pattern = r'BEGIN\s+(.*?)\s+END;'
            nested_blocks = re.findall(nested_pattern, text, re.IGNORECASE | re.DOTALL)

            for nested_block in nested_blocks:
                nested_result = extract_from_text(nested_block)
                result.extend(nested_result)

            return result

        variables = extract_from_text(block)
        return list(set(variables))

    def _extract_get_diagnostics(self, block: str) -> List[str]:
        """Извлекает переменные из GET DIAGNOSTICS"""
        variables = []
        pattern = r'GET\s+DIAGNOSTICS\s+([a-z_][a-z0-9_]*)\s*:?=\s*row_count'
        matches = re.findall(pattern, block, re.IGNORECASE)
        return matches

    # -------------------------------------------------------------------------
    # ВТОРОЙ ЭТАП: АНАЛИЗ С ПОЛЬЗОВАТЕЛЬСКИМИ РАЗМЕРАМИ
    # -------------------------------------------------------------------------
    def analyze_with_user_sizes(
        self,
        user_params: List[str],
        user_table_sizes: Dict[str, int],
        analysis_mode: Optional[str] = None,
        plan_source: Optional[str] = None,
        agent_credentials: Optional[str] = None,
        agent_scope: Optional[str] = None,
    ) -> Dict:
        """Второй этап: анализ нагрузки с пользовательскими размерами таблиц.
        analysis_mode: 'logic' | 'agent'; plan_source: 'db' | 'agent'; agent_credentials — ключ GigaChat; agent_scope — GIGACHAT_API_PERS и т.д."""
        if self.input_type == 'function':
            return self._analyze_function_with_user_sizes(
                user_params, user_table_sizes,
                analysis_mode=analysis_mode, plan_source=plan_source,
                agent_credentials=agent_credentials, agent_scope=agent_scope,
            )
        else:
            return self._analyze_query_with_user_sizes(user_params, user_table_sizes)

    # -------------------------------------------------------------------------
    # ОСНОВНОЙ МЕТОД АНАЛИЗА ФУНКЦИИ
    # -------------------------------------------------------------------------
    def _analyze_function_with_user_sizes(
        self,
        user_params: List[str],
        user_table_sizes: Dict[str, int],
        analysis_mode: Optional[str] = None,
        plan_source: Optional[str] = None,
        agent_credentials: Optional[str] = None,
        agent_scope: Optional[str] = None,
    ) -> Dict:
        """Анализ нагрузки для функции с пользовательскими размерами.
        При plan_source=='agent' планы синтезируются агентом (GigaChat), подключение к БД не обязательно."""
        function_body = '\n'.join(self.blocks)
        print("\n[DEBUG] Первые 20 строк тела функции:")
        for i, line in enumerate(function_body.split('\n')[:20]):
            print(f"  {i+1}: {line}")

        self.block_results = []
        use_agent_plan = (plan_source == 'agent' and agent_credentials)
        if use_agent_plan:
            print("\n🔍 Этап 2: Анализ нагрузки (источник плана: агент)")
            try:
                from agent.gigachat_agent import clear_agent_errors
                clear_agent_errors()
            except Exception:
                pass
        else:
            print("\n🔍 Этап 2: Анализ нагрузки функции с пользовательскими размерами")

        if not self.blocks:
            print("❌ Нет блоков для анализа")
            return {}

        print(f"Всего блоков: {len(self.blocks)}")
        if not self.conn and not use_agent_plan:
            print("❌ Нет подключения к БД (для режима «план из БД» нужно подключение)")
            return {'error': 'Нет подключения к БД', 'status': 'error'}

        print(f"[DEBUG] Параметры функции (входные): {user_params}")
        print(f"[DEBUG] Имена параметров из сигнатуры: {self.function_params}")

        param_values = {}
        if user_params and self.function_params:
            for i, param_name in enumerate(self.function_params):
                if i < len(user_params):
                    raw_val = user_params[i].strip()
                    if raw_val.startswith("'") and raw_val.endswith("'"):
                        clean_val = raw_val[1:-1]
                    else:
                        clean_val = raw_val
                    param_values[param_name] = clean_val

        print(f"[DEBUG] После сопоставления: {param_values}")

        computed_vars = self._process_variables_sequentially(function_body, param_values)

        print("\n[DEBUG] Переменные после вычисления:")
        for var, val in sorted(computed_vars.items()):
            if val is None or val == 'NULL':
                print(f"  {var} = NULL")
            elif len(str(val)) > 100:
                print(f"  {var} = {str(val)[:100]}...")
            else:
                print(f"  {var} = {val}")

        current_vars = computed_vars.copy()
        print("\n[DEBUG] Последовательное выполнение блоков:")

        last_sql_rowcount = 0
        last_sql_block_index = -1
        self.plan_cache = {}

        for idx, block in enumerate(self.blocks):
            block_type = self.block_types[idx] if idx < len(self.block_types) else 'UNKNOWN'

            # Пропускаем нетекстовые блоки
            if block_type in ['DECLARE', 'END', 'OTHER', 'CREATE', 'RETURN']:
                continue

            # Пропускаем блоки, для которых EXPLAIN не поддерживается (чтобы не засорять лог)
            if block_type in ['TRUNCATE', 'ANALYZE', 'VACUUM', 'EXPLAIN']:
                print(f"  ⏭️ Блок {block_type} пропущен (не поддерживается EXPLAIN)")
                continue

            print(f"\n--- Блок {idx+1} [{block_type}] ---")

            # Дополнительные присваивания в блоке (если есть)
            if ':=' in block:
                block_vars = self._extract_assignments_from_block_recursive(block)
                if block_vars:
                    print(f"  Найдены присваивания в блоке: {', '.join(block_vars.keys())}")
                    for var_name, expr in block_vars.items():
                        if var_name not in current_vars:
                            continue
                        if expr != 'NULL':
                            computed_expr = expr
                            for other_var, other_val in current_vars.items():
                                if other_var != var_name and other_val != 'NULL':
                                    pattern = r'\b' + re.escape(other_var) + r'\b'
                                    computed_expr = re.sub(pattern, str(other_val), computed_expr)
                            current_vars[var_name] = computed_expr
                            print(f"    ⚡ {var_name} = {computed_expr[:50]}...")

            if 'SELECT' in block.upper() and 'INTO' in block.upper():
                select_vars = self._extract_select_into_from_block(block)
                for var_name in select_vars:
                    if var_name not in current_vars:
                        continue
                    if current_vars[var_name] != 'NULL':
                        current_vars[var_name] = 'NULL'
                        print(f"    📍 {var_name} = (из SELECT INTO)")

            # Обработка EXECUTE – используем парсер
            is_execute = (block_type == 'EXECUTE' or 'EXECUTE' in block.upper())
            if is_execute:
                final_sql = self._process_execute_block(block, current_vars)
                if final_sql is None:
                    # EXECUTE format('...') INTO var USING ... — по смыслу как SELECT INTO (присвоение переменной), в блоках нагрузки не учитываем
                    print("  ⏭️ EXECUTE блок пропущен (EXECUTE … INTO … не считаем блоком нагрузки, как SELECT INTO)")
                    continue
                block_to_analyze = final_sql
                block_type_display = 'EXECUTE'
                print(f"  🔧 Разобран EXECUTE в SQL: {final_sql[:100]}...")
            else:
                block_to_analyze = block
                block_type_display = block_type

            if block_parser.is_executable_sql(block_type) or is_execute:
                # Сначала чистим PL/pgSQL конструкции (особенно SELECT INTO),
                # потом подставляем значения переменных в обычные выражения.
                clean_sql = self._clean_sql_for_explain(block_to_analyze)
                clean_sql = self._replace_variables_safe(clean_sql, current_vars)

                if clean_sql:
                    print(f"  SQL (первые 100): {clean_sql[:100]}...")
                    print(f"  [DEBUG] Полный SQL: {clean_sql}")

                    tables_in_block = SQLObjectExtractor.extract_objects(clean_sql)
                    print(f"  📋 Таблицы в блоке: {[f'{sch}.{tbl}' for sch, tbl in tables_in_block]}")

                    cache_key = hashlib.md5(clean_sql.encode()).hexdigest()
                    sizes_hash = hashlib.sha256(
                        json.dumps(user_table_sizes or {}, sort_keys=True).encode()
                    ).hexdigest()
                    plan_json = None
                    if cache_key in self.plan_cache:
                        plan_json = self.plan_cache[cache_key]
                        print(f"  🔄 Использован кэшированный план")
                    if plan_json is None:
                        try:
                            from agent.agent_cache_db import get_plan
                            plan_json = get_plan(cache_key, sizes_hash)
                            if plan_json:
                                print(f"  🔄 План из персистентного кэша (SQLite)")
                                self.plan_cache[cache_key] = plan_json
                        except Exception:
                            pass
                    if plan_json is None:
                        if use_agent_plan and agent_credentials:
                            try:
                                from agent.gigachat_agent import synthesize_plan_for_query
                                plan_json = synthesize_plan_for_query(
                                    clean_sql,
                                    [(sch, tbl) for sch, tbl in tables_in_block],
                                    credentials_override=agent_credentials,
                                    scope_override=agent_scope,
                                    user_table_sizes=user_table_sizes,
                                    params_and_vars=current_vars,
                                )
                                if plan_json:
                                    pass  # логирование в gigachat_agent.synthesize_plan_for_query
                            except ImportError:
                                plan_json = self._get_plan_for_block(clean_sql) if self.conn else None
                        else:
                            plan_json = self._get_plan_for_block(clean_sql)
                        if plan_json:
                            self.plan_cache[cache_key] = plan_json
                            try:
                                from agent.agent_cache_db import set_plan
                                set_plan(cache_key, sizes_hash, plan_json)
                            except Exception:
                                pass

                    if plan_json:
                        enhanced_plan = self.temp_table_tracker.enhance_plan_with_temp_table_stats(
                            plan_json, self.discovered_tables
                        )

                        print(f"  📊 Применение пользовательских размеров (таблиц: {len(user_table_sizes)})")
                        try:
                            adjusted_plan = plan_adjuster.apply_user_sizes_to_plan(
                                enhanced_plan,
                                user_table_sizes,
                                self.view_to_tables_map,
                                self.config.segments
                            )
                        except Exception as e:
                            print(f"⚠️ Ошибка коррекции плана: {e}")
                            adjusted_plan = enhanced_plan

                        block_load = plan_adjuster.compute_block_load(
                            adjusted_plan,
                            multipliers=self.multipliers,
                            segments=self.config.segments
                        )

                        blk = {
                            'index': idx+1,
                            'type': block_type_display,
                            'category': block_parser.get_block_category(block_type) if not is_execute else 'EXECUTE',
                            'sql_preview': clean_sql[:200] + '...',
                            'sql_full': clean_sql,
                            'plan': adjusted_plan,
                            'load': block_load,
                            'tables': [f"{sch}.{tbl}" for sch, tbl in tables_in_block]
                        }
                        self._add_antipatterns_to_block(blk, clean_sql)
                        self.block_results.append(blk)
                        print(f"  ✅ Нагрузка блока: {block_load['max_memory_gb']:.3f} GB")
                        last_sql_rowcount = block_load['total_rows']
                        last_sql_block_index = len(self.block_results) - 1
                    else:
                        block_load = plan_adjuster.estimate_block_load_from_tables(
                            tables_in_block,
                            user_table_sizes,
                            self.discovered_tables,
                            segments=self.config.segments,
                            sql=clean_sql,
                        )
                        if block_load['max_memory_gb'] > 0:
                            blk = {
                                'index': idx+1,
                                'type': block_type_display,
                                'category': block_parser.get_block_category(block_type) if not is_execute else 'EXECUTE',
                                'sql_preview': clean_sql[:200] + '...',
                                'sql_full': clean_sql,
                                'plan': None,
                                'load': block_load,
                                'tables': [f"{sch}.{tbl}" for sch, tbl in tables_in_block],
                                'fallback_estimate': True,
                            }
                            if block_load.get('heavy_reason'):
                                blk['heavy_reason'] = block_load['heavy_reason']
                            if block_load.get('heavy_recommendation'):
                                blk['heavy_recommendation'] = block_load['heavy_recommendation']
                            self._add_antipatterns_to_block(blk, clean_sql)
                            self.block_results.append(blk)
                            print(f"  ⚠️ План недоступен (таймаут/ошибка) — оценка по размерам таблиц: {block_load['max_memory_gb']:.3f} GB")
                            last_sql_rowcount = block_load['total_rows']
                            last_sql_block_index = len(self.block_results) - 1
                        else:
                            print(f"  ❌ Не удалось получить план для SQL")
                else:
                    print(f"  ⏭️ Блок не является SQL запросом после очистки")
            else:
                print(f"  ⏭️ Блок не является SQL запросом")

            if 'GET DIAGNOSTICS' in block.upper():
                if self._process_get_diagnostics_with_rowcount(block, current_vars, last_sql_rowcount):
                    print(f"    📊 GET DIAGNOSTICS обновлено с rowcount={last_sql_rowcount}")

        # ===== ДОПОЛНИТЕЛЬНЫЙ АНАЛИЗ: вложенные SQL блоки =====
        print("\n[DEBUG] АНАЛИЗ ВЛОЖЕННЫХ SQL БЛОКОВ")
        function_body = '\n'.join(self.blocks)
        nested_sql_blocks = extract_nested_sql_blocks(function_body)

        if nested_sql_blocks:
            print(f"📊 Найдено {len(nested_sql_blocks)} вложенных SQL блоков")

            for sql_block_obj in nested_sql_blocks:
                # Пропускаем дубликаты
                sql_hash = hashlib.md5(sql_block_obj.sql.encode()).hexdigest()
                if sql_hash in [hashlib.md5(b['sql_preview'][:200].encode()).hexdigest()
                            for b in self.block_results if 'sql_preview' in b]:
                    continue

                # Пропускаем блоки, не поддерживающие EXPLAIN
                if sql_block_obj.block_type in ['TRUNCATE', 'ANALYZE', 'VACUUM', 'EXPLAIN']:
                    continue

                print(f"\n  📌 {sql_block_obj.block_type} блок (линия {sql_block_obj.line_number})")

                is_execute = (sql_block_obj.block_type == 'EXECUTE' or 'EXECUTE' in sql_block_obj.sql.upper())
                if is_execute:
                    final_sql = self._process_execute_block(sql_block_obj.sql, current_vars)
                    if final_sql is None:
                        # EXECUTE … INTO … — как SELECT INTO, в блоках нагрузки не учитываем
                        print("  ⏭️ EXECUTE блок пропущен (EXECUTE … INTO … не считаем блоком нагрузки, как SELECT INTO)")
                        continue
                    sql_to_analyze = final_sql
                    block_type_display = 'EXECUTE'
                    print(f"  🔧 Разобран EXECUTE в SQL: {final_sql[:100]}...")
                else:
                    sql_to_analyze = sql_block_obj.sql
                    block_type_display = sql_block_obj.block_type

                clean_sql = self._clean_sql_for_explain(sql_to_analyze)
                clean_sql = self._replace_variables_safe(clean_sql, current_vars)

                if clean_sql:
                    print(f"    SQL: {clean_sql[:80]}...")
                    print(f"    [DEBUG] Полный SQL: {clean_sql}")

                    tables_in_block = SQLObjectExtractor.extract_objects(clean_sql)
                    print(f"    📋 Таблицы: {[f'{sch}.{tbl}' for sch, tbl in tables_in_block][:3]}")

                    cache_key = hashlib.md5(clean_sql.encode()).hexdigest()
                    sizes_hash_n = hashlib.sha256(
                        json.dumps(user_table_sizes or {}, sort_keys=True).encode()
                    ).hexdigest()
                    plan_json = None
                    if cache_key in self.plan_cache:
                        plan_json = self.plan_cache[cache_key]
                        print(f"    🔄 Кэш")
                    if plan_json is None:
                        try:
                            from agent.agent_cache_db import get_plan
                            plan_json = get_plan(cache_key, sizes_hash_n)
                            if plan_json:
                                print(f"    🔄 План из персистентного кэша")
                                self.plan_cache[cache_key] = plan_json
                        except Exception:
                            pass
                    if plan_json is None:
                        if use_agent_plan and agent_credentials:
                            try:
                                from agent.gigachat_agent import synthesize_plan_for_query
                                plan_json = synthesize_plan_for_query(
                                    clean_sql,
                                    [(sch, tbl) for sch, tbl in tables_in_block],
                                    credentials_override=agent_credentials,
                                    scope_override=agent_scope,
                                    user_table_sizes=user_table_sizes,
                                    params_and_vars=current_vars,
                                )
                                if plan_json:
                                    pass  # логирование в gigachat_agent.synthesize_plan_for_query
                            except ImportError:
                                plan_json = self._get_plan_for_block(clean_sql) if self.conn else None
                        else:
                            plan_json = self._get_plan_for_block(clean_sql)
                        if plan_json:
                            self.plan_cache[cache_key] = plan_json
                            try:
                                from agent.agent_cache_db import set_plan
                                set_plan(cache_key, sizes_hash_n, plan_json)
                            except Exception:
                                pass

                    if plan_json:
                        try:
                            adjusted_plan = plan_adjuster.apply_user_sizes_to_plan(
                                plan_json,
                                user_table_sizes,
                                self.view_to_tables_map,
                                self.config.segments
                            )
                        except Exception as e:
                            print(f"    ⚠️ Ошибка коррекции: {str(e)[:50]}")
                            adjusted_plan = plan_json

                        block_load = plan_adjuster.compute_block_load(
                            adjusted_plan,
                            multipliers=self.multipliers,
                            segments=self.config.segments
                        )

                        blk = {
                            'index': len(self.block_results) + 1,
                            'type': block_type_display,
                            'category': 'EXECUTE' if is_execute else ('DATA_QUERY' if 'SELECT' in sql_block_obj.block_type else 'DATA_MODIFICATION'),
                            'sql_preview': clean_sql[:200] + ('...' if len(clean_sql) > 200 else ''),
                            'sql_full': clean_sql,
                            'plan': adjusted_plan,
                            'load': block_load,
                            'tables': [f"{sch}.{tbl}" for sch, tbl in tables_in_block],
                            'context': sql_block_obj.block_context,
                            'line': sql_block_obj.line_number
                        }
                        self._add_antipatterns_to_block(blk, clean_sql)
                        self.block_results.append(blk)
                        print(f"    ✅ Нагрузка: {block_load['max_memory_gb']:.3f} GB")
                    else:
                        block_load = plan_adjuster.estimate_block_load_from_tables(
                            tables_in_block,
                            user_table_sizes,
                            self.discovered_tables,
                            segments=self.config.segments,
                            sql=clean_sql,
                        )
                        if block_load['max_memory_gb'] > 0:
                            blk = {
                                'index': len(self.block_results) + 1,
                                'type': block_type_display,
                                'category': 'EXECUTE' if is_execute else ('DATA_QUERY' if 'SELECT' in sql_block_obj.block_type else 'DATA_MODIFICATION'),
                                'sql_preview': clean_sql[:200] + ('...' if len(clean_sql) > 200 else ''),
                                'sql_full': clean_sql,
                                'plan': None,
                                'load': block_load,
                                'tables': [f"{sch}.{tbl}" for sch, tbl in tables_in_block],
                                'context': sql_block_obj.block_context,
                                'line': sql_block_obj.line_number,
                                'fallback_estimate': True,
                            }
                            if block_load.get('heavy_reason'):
                                blk['heavy_reason'] = block_load['heavy_reason']
                            if block_load.get('heavy_recommendation'):
                                blk['heavy_recommendation'] = block_load['heavy_recommendation']
                            self._add_antipatterns_to_block(blk, clean_sql)
                            self.block_results.append(blk)
                            print(f"    ⚠️ План недоступен — оценка по размерам: {block_load['max_memory_gb']:.3f} GB")

        total_load = self._calculate_total_load(self.block_results)
        top_blocks = self._get_top_blocks(self.block_results, 3)

        result = {
            'input_type': 'function',
            'function': self.func_name,
            'blocks_count': len(self.blocks),
            'analyzed_blocks': len(self.block_results),
            'total_memory_gb': total_load['total_memory_gb'],
            'antipattern_added_gb': total_load.get('antipattern_added_gb', 0),
            'max_utilization': total_load['max_utilization'],
            'risk': total_load['risk'],
            'estimated_time_sec': total_load['estimated_time_sec'],
            'user_params': user_params,
            'user_table_sizes': user_table_sizes,
            'discovered_tables': self.discovered_tables,
            'temp_tables': list(self.temp_tables),
            'variables': current_vars,
            'top_blocks': [
                {
                    'index': b['index'],
                    'type': b['type'],
                    'category': b['category'],
                    'max_memory_gb': b['load']['max_memory_gb'],
                    'sql_preview': b['sql_preview'],
                    'tables': b['tables']
                } for b in top_blocks
            ],
            'block_details': [
                {
                    'index': b['index'],
                    'type': b['type'],
                    'category': b['category'],
                    'max_memory_gb': b['load']['max_memory_gb'],
                    'total_rows': b['load']['total_rows'],
                    'sql_preview': b['sql_preview'],
                    'tables': b['tables'],
                    **({k: b[k] for k in ('fallback_estimate', 'heavy_reason', 'heavy_recommendation', 'anti_patterns', 'block_hedge') if k in b}),
                } for b in self.block_results
            ],
            'problematic_blocks': [
                {'index': b['index'], 'type': b['type'], 'anti_patterns': b['anti_patterns'], 'block_hedge': b.get('block_hedge', []), 'max_memory_gb': b['load']['max_memory_gb'], 'tables': b['tables'], 'sql_full': b.get('sql_full', b.get('sql_preview', ''))}
                for b in self.block_results if b.get('anti_patterns')
            ],
            'general_hedge_recommendations': GENERAL_HEDGE_RECOMMENDATIONS,
            'agent_errors': self._get_agent_errors(),
            'timestamp': datetime.now().isoformat()
        }

        self._print_detailed_report(result)
        return result

    # -------------------------------------------------------------------------
    # АНАЛИЗ ОБЫЧНОГО SQL ЗАПРОСА
    # -------------------------------------------------------------------------
    def _analyze_query_with_user_sizes(self, user_params: List[str], user_table_sizes: Dict[str, int]) -> Dict:
        """Анализ нагрузки для обычного SQL запроса"""
        self.block_results = []
        print("\n🔍 Анализ нагрузки SQL запроса с пользовательскими размерами")

        if not self.blocks:
            print("❌ Нет блоков для анализа")
            return {}

        if not self.conn:
            print("❌ Нет подключения к БД")
            return {'error': 'Нет подключения к БД', 'status': 'error'}

        # Создаем хеш от пользовательских размеров для версионирования кэша
        sizes_hash = hashlib.md5(str(sorted(user_table_sizes.items())).encode()).hexdigest()
        versioned_cache_key = f"plan_cache_{sizes_hash}"

        if not hasattr(self, 'versioned_plan_cache'):
            self.versioned_plan_cache = {}

        if versioned_cache_key not in self.versioned_plan_cache:
            self.versioned_plan_cache[versioned_cache_key] = {}
            print(f"🆕 Создан новый кэш планов для текущих размеров")

        current_cache = self.versioned_plan_cache[versioned_cache_key]

        for idx, block in enumerate(self.blocks):
            block_type = self.block_types[idx] if idx < len(self.block_types) else 'UNKNOWN'

            print(f"\n--- Блок {idx+1} [{block_type}] ---")

            if not block_parser.is_executable_sql(block_type):
                continue

            # Пропускаем блоки, не поддерживающие EXPLAIN
            if block_type in ['TRUNCATE', 'ANALYZE', 'VACUUM', 'EXPLAIN']:
                print(f"  ⏭️ Блок {block_type} пропущен (не поддерживается EXPLAIN)")
                continue

            clean_sql = self._clean_sql_for_explain(block)
            if not clean_sql:
                continue

            print(f"  SQL (первые 100): {clean_sql[:100]}...")
            print(f"  [DEBUG] Полный SQL: {clean_sql}")

            tables_in_block = SQLObjectExtractor.extract_objects(clean_sql)
            print(f"  📋 Таблицы в блоке: {[f'{sch}.{tbl}' for sch, tbl in tables_in_block]}")

            cache_key = hashlib.md5(clean_sql.encode()).hexdigest()
            if cache_key in current_cache:
                plan_json = current_cache[cache_key]
                print(f"  🔄 Использован кэшированный план (версия {sizes_hash[:8]})")
            else:
                plan_json = self._get_plan_for_block(clean_sql)
                if plan_json:
                    current_cache[cache_key] = plan_json
                    print(f"  ✅ Получен новый план")

            if plan_json:
                enhanced_plan = self.temp_table_tracker.enhance_plan_with_temp_table_stats(
                    plan_json, self.discovered_tables
                )

                print(f"  📊 Применение пользовательских размеров (таблиц: {len(user_table_sizes)})")
                try:
                    adjusted_plan = plan_adjuster.apply_user_sizes_to_plan(
                        enhanced_plan,
                        user_table_sizes,
                        self.view_to_tables_map,
                        self.config.segments
                    )
                except Exception as e:
                    print(f"⚠️ Ошибка коррекции плана: {e}")
                    adjusted_plan = enhanced_plan

                block_load = plan_adjuster.compute_block_load(
                    adjusted_plan,
                    multipliers=self.multipliers,
                    segments=self.config.segments
                )

                blk = {
                    'index': idx+1,
                    'type': block_type,
                    'category': block_parser.get_block_category(block_type),
                    'sql_preview': clean_sql[:200] + '...',
                    'sql_full': clean_sql,
                    'plan': adjusted_plan,
                    'load': block_load,
                    'tables': [f"{sch}.{tbl}" for sch, tbl in tables_in_block]
                }
                self._add_antipatterns_to_block(blk, clean_sql)
                self.block_results.append(blk)
                print(f"  ✅ Нагрузка блока: {block_load['max_memory_gb']:.3f} GB")
            else:
                block_load = plan_adjuster.estimate_block_load_from_tables(
                    tables_in_block,
                    user_table_sizes,
                    self.discovered_tables,
                    segments=self.config.segments,
                    sql=clean_sql,
                )
                if block_load['max_memory_gb'] > 0:
                    blk = {
                        'index': idx+1,
                        'type': block_type,
                        'category': block_parser.get_block_category(block_type),
                        'sql_preview': clean_sql[:200] + '...',
                        'sql_full': clean_sql,
                        'plan': None,
                        'load': block_load,
                        'tables': [f"{sch}.{tbl}" for sch, tbl in tables_in_block],
                        'fallback_estimate': True,
                    }
                    if block_load.get('heavy_reason'):
                        blk['heavy_reason'] = block_load['heavy_reason']
                    if block_load.get('heavy_recommendation'):
                        blk['heavy_recommendation'] = block_load['heavy_recommendation']
                    self._add_antipatterns_to_block(blk, clean_sql)
                    self.block_results.append(blk)
                    print(f"  ⚠️ План недоступен — оценка по размерам: {block_load['max_memory_gb']:.3f} GB")
                else:
                    print(f"  ❌ Не удалось получить план для SQL")

        total_load = self._calculate_total_load(self.block_results)
        top_blocks = self._get_top_blocks(self.block_results, 3)

        result = {
            'input_type': 'query',
            'blocks_count': len(self.blocks),
            'analyzed_blocks': len(self.block_results),
            'total_memory_gb': total_load['total_memory_gb'],
            'antipattern_added_gb': total_load.get('antipattern_added_gb', 0),
            'max_utilization': total_load['max_utilization'],
            'risk': total_load['risk'],
            'estimated_time_sec': total_load['estimated_time_sec'],
            'user_params': user_params,
            'user_table_sizes': user_table_sizes,
            'discovered_tables': self.discovered_tables,
            'temp_tables': list(self.temp_tables),
            'top_blocks': [
                {
                    'index': b['index'],
                    'type': b['type'],
                    'category': b['category'],
                    'max_memory_gb': b['load']['max_memory_gb'],
                    'sql_preview': b['sql_preview'],
                    'tables': b['tables']
                } for b in top_blocks
            ],
            'block_details': [
                {
                    'index': b['index'],
                    'type': b['type'],
                    'category': b['category'],
                    'max_memory_gb': b['load']['max_memory_gb'],
                    'total_rows': b['load']['total_rows'],
                    'sql_preview': b['sql_preview'],
                    'tables': b['tables'],
                    **({k: b[k] for k in ('fallback_estimate', 'heavy_reason', 'heavy_recommendation', 'anti_patterns', 'block_hedge') if k in b}),
                } for b in self.block_results
            ],
            'problematic_blocks': [
                {'index': b['index'], 'type': b['type'], 'anti_patterns': b['anti_patterns'], 'block_hedge': b.get('block_hedge', []), 'max_memory_gb': b['load']['max_memory_gb'], 'tables': b['tables'], 'sql_full': b.get('sql_full', b.get('sql_preview', ''))}
                for b in self.block_results if b.get('anti_patterns')
            ],
            'general_hedge_recommendations': GENERAL_HEDGE_RECOMMENDATIONS,
            'agent_errors': self._get_agent_errors(),
            'timestamp': datetime.now().isoformat()
        }

        self._print_detailed_report(result)
        return result

    def _get_agent_errors(self) -> List[Dict]:
        """Возвращает ошибки агента (не решённые пересчётом) для вкладки сводки."""
        try:
            from agent.gigachat_agent import get_recent_agent_errors
            return get_recent_agent_errors()
        except Exception:
            return []

    def _add_antipatterns_to_block(self, blk: Dict, clean_sql: str) -> None:
        """Добавляет anti_patterns и block_hedge в блок при обнаружении антипаттернов."""
        ap_list = detect_antipatterns(clean_sql)
        if ap_list:
            blk['anti_patterns'] = ap_list
            blk['block_hedge'] = get_hedge_recommendations(ap_list)

    # -------------------------------------------------------------------------
    # ВЫЧИСЛЕНИЕ НАГРУЗКИ И ОТЧЁТ
    # -------------------------------------------------------------------------
    def _calculate_total_load(self, block_results: List[Dict]) -> Dict:
        """Вычисляет суммарную нагрузку с учётом антипаттернов (доп. нагрузка на скейле)."""
        from .antipattern_detector import get_antipattern_load_multiplier

        total_memory_gb = 0.0
        antipattern_added_gb = 0.0
        for b in block_results:
            base_gb = b['load']['max_memory_gb']
            mult = get_antipattern_load_multiplier(
                b.get('anti_patterns') or [],
                block_max_memory_gb=base_gb,
            )
            adjusted_gb = base_gb * mult
            total_memory_gb += adjusted_gb
            if mult > 1.0:
                antipattern_added_gb += (adjusted_gb - base_gb)

        max_utilization = total_memory_gb / self.config.ram_per_seg_gb * 100 if self.config.ram_per_seg_gb > 0 else 0

        if max_utilization > 40:
            risk = "ВЫСОКИЙ"
        elif max_utilization > 15:
            risk = "СРЕДНИЙ"
        else:
            risk = "НИЗКИЙ"

        estimated_time_sec = total_memory_gb * 10

        return {
            'total_memory_gb': round(total_memory_gb, 2),
            'antipattern_added_gb': round(antipattern_added_gb, 2),
            'max_utilization': round(max_utilization, 2),
            'risk': risk,
            'estimated_time_sec': round(estimated_time_sec, 2)
        }

    def _get_top_blocks(self, block_results: List[Dict], top_n: int = 3) -> List[Dict]:
        """Возвращает топ-N блоков по нагрузке"""
        sorted_blocks = sorted(block_results, key=lambda x: x['load']['max_memory_gb'], reverse=True)
        return sorted_blocks[:top_n]

    def _get_plan_for_block(self, sql: str) -> Optional[dict]:
        """Выполняет EXPLAIN для SQL-запроса"""
        if not self.conn:
            return None
        try:
            explain_sql = f"EXPLAIN (VERBOSE, COSTS, FORMAT JSON) {sql}"
            result = self._execute_query(explain_sql)
            if result and result[0] and result[0][0]:
                plan_data = result[0][0]
                if isinstance(plan_data, list) and len(plan_data) > 0:
                    return plan_data[0]
                return plan_data
        except Exception as e:
            print(f"⚠️ Ошибка EXPLAIN: {e}")
            print(f"  [DEBUG] Проблемный SQL: {sql}")
        return None

    def _print_detailed_report(self, result: Dict):
        """Печать итогового отчёта"""
        print("\n" + "="*80)
        print("ИТОГОВЫЙ ОТЧЁТ ДЕТАЛЬНОГО АНАЛИЗА")
        print("="*80)

        if result.get('input_type') == 'function':
            print(f"Тип: Функция")
            print(f"Функция: {result.get('function', 'unknown')}")
        else:
            print(f"Тип: SQL запрос")

        total = result['blocks_count']
        analyzed = result['analyzed_blocks']
        skipped = total - analyzed
        print(f"Всего блоков: {total}, проанализировано: {analyzed}")
        if skipped > 0:
            print(f"Пропущено: {skipped} (TRUNCATE/ANALYZE/VACUUM или EXECUTE INTO — не оцениваются по плану)")

        if result.get('temp_tables'):
            print(f"\n📋 Временные таблицы: {', '.join(result['temp_tables'])}")

        if result.get('discovered_tables'):
            print(f"\n📊 ФИЗИЧЕСКИЕ ТАБЛИЦЫ:")
            for table, info in result['discovered_tables'].items():
                user_info = ""
                if table in result.get('user_table_sizes', {}):
                    user_info = f" (пользовательские: {result['user_table_sizes'][table]:,})"
                print(f"  • {table}: {info['current_rows']:,} строк, {info['size_gb']:.3f} GB{user_info}")

        if result.get('user_params'):
            print(f"\n📋 Параметры: {', '.join(result['user_params'])}")

        print(f"\nТОП-3 САМЫХ ТЯЖЁЛЫХ ЗАПРОСА:")
        for i, b in enumerate(result['top_blocks'], 1):
            print(f"{i}. Блок {b['index']} [{b['type']}/{b['category']}]: {b['max_memory_gb']:.3f} GB")
            print(f"   Таблицы: {', '.join(b['tables'])}")
            print(f"   SQL: {b['sql_preview'][:100]}...")
        print(f"\nСУММАРНАЯ НАГРУЗКА: {result['total_memory_gb']:.2f} GB")
        if result.get('antipattern_added_gb', 0) > 0:
            print(f"  (в т.ч. +{result['antipattern_added_gb']:.2f} GB от антипаттернов на скейле)")
        print(f"МАКСИМАЛЬНАЯ УТИЛИЗАЦИЯ: {result['max_utilization']:.1f}% RAM/сегмент")
        print(f"РИСК: {result['risk']}")
        print(f"ОЦЕНОЧНОЕ ВРЕМЯ ВЫПОЛНЕНИЯ: {result['estimated_time_sec']:.2f} сек")
        print("="*80)