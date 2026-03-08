import re
import json
import psycopg2
import hashlib
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime, timedelta
from dataclasses import dataclass

from . import block_parser
from . import plan_adjuster
from . import load_calculator
from .temp_table_tracker import TempTableTracker


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
        self.input_type = None  # 'function' или 'query'
        self.view_to_tables_map = {}  # маппинг представление -> физические таблицы
        self.plan_cache = {}  # кэш для планов запросов
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
    
    def reset_for_rerun(self):
        """
        Сбрасывает состояние анализатора для повторного запуска
        Очищает результаты предыдущего анализа, сохраняя discovery данные
        """
        print("🔄 Сброс состояния анализатора для повторного запуска")
        self.block_results = []
        self.variables = {}  # Очищаем переменные
        # Не очищаем весь кэш, только текущую версию
        if hasattr(self, 'versioned_plan_cache'):
            # Оставляем версионированный кэш, он будет использован для соответствующих размеров
            pass
    
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
        
        # Если нет признаков функции - считаем запросом
        return 'query'
    
    def _extract_function_body(self, ddl: str) -> str:
        """
        Извлекает тело функции из DDL.
        Если это не функция, возвращает исходный текст.
        """
        if 'FUNCTION' not in ddl.upper():
            return ddl  # Это обычный запрос
        
        patterns = [
            r'AS\s*\$\$\s*(.*?)\s*\$\$\s*(?:LANGUAGE|EXECUTE|VOLATILE|IMMUTABLE|STABLE|SECURITY|COST|ROWS|SET|FROM|$$|$)',
            r'AS\s*\$\$([\s\S]*?)\$\$',
        ]
        
        for pattern in patterns:
            body_match = re.search(pattern, ddl, re.IGNORECASE | re.DOTALL)
            if body_match:
                body = body_match.group(1).strip()
                if body:
                    return body
        return ddl
    
    def _extract_objects_from_sql(self, sql: str) -> List[Tuple[str, str]]:
        """Извлекает объекты schema.table из SQL"""
        objects = []
        pattern = r'(?:from|join|update|insert\s+into|into|using|table)\s+([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]+)'
        matches = re.findall(pattern, sql, re.IGNORECASE)
        seen = set()
        for sch, tbl in matches:
            key = (sch.lower(), tbl.lower())
            if key not in seen:
                objects.append((sch, tbl))
                seen.add(key)
        return objects
    
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
    
    def _parse_declare_section(self, body: str) -> Dict[str, Tuple[str, int]]:
        """Парсит секцию DECLARE - улучшенная версия"""
        variables = {}
        
        # Ищем секцию DECLARE до первого BEGIN
        declare_match = re.search(r'DECLARE\s+(.*?)BEGIN', body, re.IGNORECASE | re.DOTALL)
        if not declare_match:
            print("    [DEBUG] Секция DECLARE не найдена")
            return variables
        
        declare_section = declare_match.group(1)
        print(f"    [DEBUG] Секция DECLARE: {declare_section[:200]}...")
        
        # Разбиваем на строки для построчной обработки
        lines = declare_section.split('\n')
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line or line.startswith('--'):
                continue
            
            # Убираем точку с запятой в конце
            if line.endswith(';'):
                line = line[:-1]
            
            print(f"    [DEBUG] Обработка строки {line_num}: {line}")
            
            # Паттерн для объявления переменной: имя тип [:= значение]
            # Учитываем, что тип может быть составным (schema.type)
            pattern = r'^\s*([a-z_][a-z0-9_]*)\s+([a-z_][a-z0-9_.]+)(?:\s*:=\s*(.*?))?\s*$'
            match = re.match(pattern, line, re.IGNORECASE)
            
            if match:
                var_name = match.group(1)
                var_type = match.group(2)
                var_value = match.group(3) if match.group(3) else 'NULL'
                
                if var_value != 'NULL':
                    var_value = var_value.strip()
                
                variables[var_name] = (var_value, line_num)
                print(f"    ✅ Найдена переменная: {var_name} ({var_type}) = {var_value}")
            else:
                print(f"    ❌ Не удалось распарсить: {line}")
        
        return variables

    
    def _process_variables_sequentially(self, body: str, param_values: Dict[str, str]) -> Dict[str, str]:
        """
        Последовательно обрабатывает переменные в порядке их появления в коде.
        """
        print("\n📋 [DEBUG] Начало обработки переменных")
        print(f"[DEBUG] Параметры: {param_values}")
        
        # Получаем начальные значения из DECLARE
        declare_vars = self._parse_declare_section(body)
        variables = {}
        
        # Добавляем переменные из DECLARE
        for name, (value, line) in declare_vars.items():
            variables[name] = value
            print(f"  [DECLARE] {name} = {value}")
        
        # Добавляем параметры
        for param_name, param_value in param_values.items():
            variables[param_name] = param_value
            print(f"  [PARAM] {param_name} = {param_value}")
        
        # Находим начало тела функции
        body_upper = body.upper()
        begin_pos = body_upper.find('BEGIN')
        if begin_pos == -1:
            print("  [WARN] Не найдено BEGIN в теле функции")
            return variables
        
        # Берем весь код после BEGIN
        main_body = body[begin_pos + 5:].strip()
        
        # Разбиваем на блоки по точке с запятой, но с учетом вложенных BEGIN/END
        blocks = []
        current_block = []
        depth = 0
        in_string = False
        
        for char in main_body:
            current_block.append(char)
            
            if char == "'" and (len(current_block) == 1 or current_block[-2] != '\\'):
                in_string = not in_string
            
            if not in_string:
                if char == ';' and depth == 0:
                    blocks.append(''.join(current_block).strip())
                    current_block = []
                elif char == 'b' and ''.join(current_block[-5:]).upper() == 'BEGIN':
                    depth += 1
                elif char == 'd' and ''.join(current_block[-3:]).upper() == 'END':
                    depth -= 1
        
        if current_block:
            blocks.append(''.join(current_block).strip())
        
        print(f"\n[DEBUG] Найдено {len(blocks)} блоков для обработки")
        
        # Множественные проходы для учета зависимостей
        max_passes = 10
        for pass_num in range(max_passes):
            changed = False
            print(f"\n[DEBUG] Проход {pass_num + 1}:")
            
            for block in blocks:
                # Пропускаем SQL запросы
                if re.match(r'^\s*(SELECT|INSERT|UPDATE|DELETE|TRUNCATE)', block, re.IGNORECASE):
                    continue
                
                # Ищем присваивания (включая вложенные)
                if ':=' in block:
                    # Извлекаем все присваивания из блока
                    assign_pattern = r'([a-z_][a-z0-9_]*)\s*:=\s*(.*?);'
                    matches = re.findall(assign_pattern, block, re.IGNORECASE | re.DOTALL)
                    
                    for var_name, expr in matches:
                        # Очищаем выражение
                        expr = ' '.join(expr.split())
                        
                        # Подставляем известные переменные
                        computed_expr = expr
                        for other_var, other_val in variables.items():
                            if other_var != var_name and other_val != 'NULL':
                                pattern = r'\b' + re.escape(other_var) + r'\b'
                                if re.search(pattern, computed_expr):
                                    computed_expr = re.sub(pattern, str(other_val), computed_expr)
                        
                        # Проверяем, остались ли неизвестные переменные
                        remaining_vars = re.findall(r'\b[a-z_][a-z0-9_]*\b', computed_expr)
                        unknown_exists = False
                        for v in remaining_vars:
                            if v != var_name and v not in variables:
                                unknown_exists = True
                                break
                        
                        # Если все переменные известны, сохраняем значение
                        if not unknown_exists:
                            if var_name not in variables or variables[var_name] != computed_expr:
                                variables[var_name] = computed_expr
                                changed = True
                                print(f"    ⚡ {var_name} = {computed_expr[:50]}...")
                
                # Ищем SELECT INTO
                if 'SELECT' in block.upper() and 'INTO' in block.upper():
                    into_pattern = r'SELECT\s+.*?\s+INTO\s+([\w\s_,]+?)\s+FROM'
                    into_matches = re.findall(into_pattern, block, re.IGNORECASE | re.DOTALL)
                    
                    for into_clause in into_matches:
                        for var_name in [v.strip() for v in into_clause.split(',')]:
                            if var_name and var_name not in variables:
                                variables[var_name] = 'NULL'
                                changed = True
                                print(f"    📍 {var_name} = (из SELECT INTO)")
            
            if not changed:
                print(f"    Нет изменений, останов на проходе {pass_num + 1}")
                break
        
        # Выводим финальные значения
        print("\n[DEBUG] Все переменные после обработки:")
        for var, val in sorted(variables.items()):
            if val is None or val == 'NULL':
                print(f"  {var} = NULL")
            elif len(str(val)) > 100:
                print(f"  {var} = {str(val)[:100]}...")
            else:
                print(f"  {var} = {val}")
        
        return variables
    

    def _is_expression(self, value: str) -> bool:
        """Определяет, является ли значение выражением, а не константой"""
        if not value:
            return False
        
        if value == 'NULL' or value == '':
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
    
    def _clean_sql_for_explain(self, sql: str) -> str:
        """
        Очищает SQL от INTO переменных и других PL/pgSQL конструкций.
        """
        sql = re.sub(r'\s+INTO\s+[\w\s,]+(\s+FROM)', r'\1', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\s+INTO\s+[\w\s,]+$', '', sql, flags=re.IGNORECASE)
        sql = re.sub(r'(SELECT.*?)\s+INTO\s+[\w\s,]+(\s+FROM)', r'\1\2', sql, flags=re.IGNORECASE | re.DOTALL)
        
        if re.match(r'^\s*PERFORM\s+', sql, re.IGNORECASE):
            return ''
        
        if re.match(r'^\s*RETURN\s+', sql, re.IGNORECASE):
            return ''
        
        if re.match(r'^\s*GET\s+DIAGNOSTICS', sql, re.IGNORECASE):
            return ''
        
        sql = re.sub(r"::'(\d{4}-\d{2}-\d{2})'", r"::date", sql)
        sql = re.sub(r"'(\d{4}-\d{2}-\d{2})'::\w+", r"'\1'::date", sql)
        
        insert_match = re.search(r'insert\s+([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]+)', sql, re.IGNORECASE)
        if insert_match and 'insert into' not in sql.lower():
            schema = insert_match.group(1)
            table = insert_match.group(2)
            sql = re.sub(r'insert\s+([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]+)', 
                        f'insert into {schema}.{table}', sql, flags=re.IGNORECASE)
        
        sql = re.sub(r'insert\s+into\s+into', 'insert into', sql, flags=re.IGNORECASE)
        
        return sql.strip()
    
    def _replace_variables(self, sql: str, variables: Dict[str, str]) -> str:
        """Заменяет переменные на значения в SQL с учётом типа данных"""
        print(f"\n[DEBUG] Замена переменных в SQL")
        
        result = sql
        
        for var_name in sorted(variables.keys(), key=len, reverse=True):
            var_value = variables[var_name]
            
            if var_value == '':
                replacement = 'NULL'
            elif var_value == 'current_date':
                replacement = 'CURRENT_DATE'
            elif self._is_expression(var_value):
                replacement = var_value
            elif var_value == 'NULL':
                replacement = 'NULL'
            elif re.match(r'^\d{4}-\d{2}-\d{2}$', var_value):
                replacement = f"'{var_value}'::date"
            elif re.match(r'^-?\d+(\.\d+)?$', var_value):
                replacement = var_value
            else:
                replacement = f"'{var_value}'"
            
            pattern = r'\b' + re.escape(var_name) + r'\b'
            if re.search(pattern, result):
                result = re.sub(pattern, replacement, result)
                print(f"    Заменяем {var_name} -> {replacement[:50]}...")
        
        return result

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
        
        # Определяем тип входных данных
        self.input_type = self._detect_input_type(sql_text)
        print(f"🔍 Обнаружен тип входных данных: {self.input_type}")
        
        if self.input_type == 'function':
            return self._discover_tables_from_function(sql_text, user_params)
        else:
            return self._discover_tables_from_query(sql_text, user_params)
    
    def _discover_tables_from_function(self, ddl: str, user_params: List[str] = None) -> Dict[str, Any]:
        """Обнаружение таблиц из функции"""
        print("🔍 Этап 1: Обнаружение таблиц в DDL функции")
        
        # Извлекаем тело функции
        function_body = self._extract_function_body(ddl)
        print(f"📄 Извлечено тело функции, длина: {len(function_body)} символов")
        
        # Находим временные таблицы
        self.temp_tables = block_parser.extract_temp_tables_from_ddl(function_body)
        if self.temp_tables:
            print(f"📋 Найдены временные таблицы: {', '.join(self.temp_tables)}")
        
        # Парсим сигнатуру функции
        self.func_name, self.function_params = self._parse_function_signature(ddl)
        print(f"📋 Функция: {self.func_name}")
        if self.function_params:
            print(f"📋 Параметры функции: {', '.join(self.function_params)}")
        
        # Сопоставляем параметры с пользовательскими значениями
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
        
        # Обрабатываем переменные
        if function_body:
            self.variables = self._process_variables_sequentially(function_body, param_values)
            print(f"📊 Вычислено {len(self.variables)} переменных")
        
        # Разбиваем тело функции на блоки
        self.blocks = block_parser.split_sql_blocks(function_body)
        self.block_types = [block_parser.classify_block(block) for block in self.blocks]
        
        # Статистика по типам блоков
        type_stats = {}
        for block_type in self.block_types:
            type_stats[block_type] = type_stats.get(block_type, 0) + 1
        
        print(f"🧩 Найдено {len(self.blocks)} логических блоков в теле функции:")
        for block_type, count in sorted(type_stats.items()):
            print(f"  • {block_type}: {count}")
        
        # Собираем все объекты из выполняемых блоков
        all_objects = set()
        view_definitions = {}
        
        for i, block in enumerate(self.blocks):
            block_type = self.block_types[i]
            
            if not block_parser.is_executable_sql(block_type):
                continue
            
            block_with_vars = self._replace_variables(block, self.variables)
            clean_sql = self._clean_sql_for_explain(block_with_vars)
            if not clean_sql:
                continue
            
            objects = self._extract_objects_from_sql(clean_sql)
            for sch, tbl in objects:
                all_objects.add((sch, tbl))
        
        print(f"📋 Найдено {len(all_objects)} объектов (таблиц/представлений) в SQL-запросах")
        
        if not self.conn:
            print("❌ Нет подключения к БД. Невозможно раскрыть представления.")
            return {
                'input_type': 'function',
                'function': self.func_name,
                'blocks_count': len(self.blocks),
                'block_types': self.block_types,
                'temp_tables': list(self.temp_tables),
                'discovered_tables': {},
                'variables': self.variables,
                'status': 'error',
                'error': 'Нет подключения к БД'
            }
        
        # Если есть подключение, получаем определения представлений
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
            'variables': self.variables,
            'status': 'tables_discovered'
        }
    
    def _discover_tables_from_query(self, query: str, user_params: List[str] = None) -> Dict[str, Any]:
        """Обнаружение таблиц в обычном SQL запросе"""
        print("🔍 Этап 1: Обнаружение таблиц в SQL запросе")
        
        # Очищаем запрос от параметров если они есть
        clean_query = query
        if user_params:
            # Простая замена позиционных параметров
            for i, param in enumerate(user_params, 1):
                placeholder = f"${i}"
                if param.startswith("'") and param.endswith("'"):
                    clean_query = clean_query.replace(placeholder, param)
                else:
                    clean_query = clean_query.replace(placeholder, f"'{param}'")
        
        # Разбиваем запрос на блоки (для CTE и подзапросов)
        self.blocks = block_parser.split_sql_blocks(clean_query)
        self.block_types = [block_parser.classify_block(block) for block in self.blocks]
        
        print(f"🧩 Найдено {len(self.blocks)} логических блоков в запросе")
        
        # Собираем все объекты из запроса
        all_objects = set()
        view_definitions = {}
        
        for i, block in enumerate(self.blocks):
            objects = self._extract_objects_from_sql(block)
            for sch, tbl in objects:
                all_objects.add((sch, tbl))
        
        print(f"📋 Найдено {len(all_objects)} объектов (таблиц/представлений) в запросе")
        
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
    
    def _extract_assignments_from_block(self, block: str) -> Dict[str, str]:
        """Извлекает все присваивания := из блока"""
        assignments = {}
        
        pattern = r'([a-z_][a-z0-9_]*)\s*:=\s*(.*?);'
        matches = re.findall(pattern, block, re.IGNORECASE | re.DOTALL)
        
        for var_name, expr in matches:
            expr = ' '.join(expr.split())
            assignments[var_name] = expr
        
        return assignments

    def _extract_get_diagnostics(self, block: str) -> List[str]:
        """Извлекает переменные из GET DIAGNOSTICS"""
        variables = []
        pattern = r'GET\s+DIAGNOSTICS\s+([a-z_][a-z0-9_]*)\s*:?=\s*row_count'
        matches = re.findall(pattern, block, re.IGNORECASE)
        return matches

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

    def analyze_with_user_sizes(self, user_params: List[str], user_table_sizes: Dict[str, int]) -> Dict:
        """Второй этап: анализ нагрузки с пользовательскими размерами таблиц."""
        
        if self.input_type == 'function':
            return self._analyze_function_with_user_sizes(user_params, user_table_sizes)
        else:
            return self._analyze_query_with_user_sizes(user_params, user_table_sizes)

    def _analyze_function_with_user_sizes(self, user_params: List[str], user_table_sizes: Dict[str, int]) -> Dict:
        """Анализ нагрузки для функции с оптимизацией"""
        function_body = '\n'.join(self.blocks)
        print("\n[DEBUG] Первые 20 строк тела функции:")
        for i, line in enumerate(function_body.split('\n')[:20]):
            print(f"  {i+1}: {line}")

        self.block_results = []
        print("\n🔍 Этап 2: Анализ нагрузки функции с пользовательскими размерами")
        
        if not self.blocks:
            print("❌ Нет блоков для анализа")
            return {}
        
        if not self.conn:
            print("❌ Нет подключения к БД")
            return {'error': 'Нет подключения к БД', 'status': 'error'}
        
        print(f"[DEBUG] Параметры функции (входные): {user_params}")
        print(f"[DEBUG] Имена параметров из сигнатуры: {self.function_params}")
        
        # Подготавливаем параметры
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
        
        # Получаем начальные значения из DECLARE
        print("\n[DEBUG] Парсинг секции DECLARE:")
        function_body = '\n'.join(self.blocks)
        declare_vars = self._parse_declare_section(function_body)
        print("\n[DEBUG] Начальные переменные из DECLARE:")
        
        current_vars = {}
        
        for var_name, (var_value, line) in declare_vars.items():
            current_vars[var_name] = var_value
            print(f"  {var_name} = {var_value}")
        
        for param_name, param_value in param_values.items():
            current_vars[param_name] = param_value
            print(f"  [PARAM] {param_name} = {param_value}")
        
        # Принудительное вычисление ключевых переменных
        if 'p_run_dt' in current_vars:
            p_run_dt = current_vars['p_run_dt']
            if p_run_dt == 'current_date':
                current_vars['v_run_dt'] = 'CURRENT_DATE'
            else:
                current_vars['v_run_dt'] = f"'{p_run_dt}'::date"
            print(f"  [ВЫЧИСЛЕНО] v_run_dt = {current_vars['v_run_dt']}")
        
        if 'p_hist_depth' in current_vars:
            current_vars['v_hist_start'] = f"'{current_vars['p_hist_depth']}'::date"
            print(f"  [ВЫЧИСЛЕНО] v_hist_start = {current_vars['v_hist_start']}")
        
        if 'v_run_dt' in current_vars:
            v_run_dt = current_vars['v_run_dt']
            current_vars['v_prev_run_dt'] = f"({v_run_dt} - interval '1 day')::date"
            current_vars['v_prev_two_month_end_eom'] = f"(date_trunc('month', {v_run_dt} - interval '2 months') + interval '1 month' - interval '1 day')::date"
            current_vars['v_prev_month_start'] = f"date_trunc('month', {v_run_dt} - interval '1 month')::date"
            current_vars['v_curr_month_start'] = f"date_trunc('month', {v_run_dt})::date"
            current_vars['v_next_month_start'] = f"date_trunc('month', {v_run_dt} + interval '1 month')::date"
            print(f"  [ВЫЧИСЛЕНО] v_prev_run_dt = {current_vars['v_prev_run_dt']}")
            print(f"  [ВЫЧИСЛЕНО] v_prev_two_month_end_eom = {current_vars['v_prev_two_month_end_eom']}")
            print(f"  [ВЫЧИСЛЕНО] v_prev_month_start = {current_vars['v_prev_month_start']}")
            print(f"  [ВЫЧИСЛЕНО] v_curr_month_start = {current_vars['v_curr_month_start']}")
            print(f"  [ВЫЧИСЛЕНО] v_next_month_start = {current_vars['v_next_month_start']}")
        
        if 'p_reload_start_date' in current_vars and current_vars['p_reload_start_date']:
            reload_start = current_vars['p_reload_start_date']
            current_vars['v_reload_start'] = f"date_trunc('month', '{reload_start}'::date)::date"
            print(f"  [ВЫЧИСЛЕНО] v_reload_start = {current_vars['v_reload_start']} (из p_reload_start_date)")
        elif 'v_run_dt' in current_vars and 'p_hist_reload_months' in current_vars:
            v_run_dt = current_vars['v_run_dt']
            months = current_vars['p_hist_reload_months']
            current_vars['v_reload_start'] = f"date_trunc('month', {v_run_dt} - (interval '1 month') * {months})::date"
            print(f"  [ВЫЧИСЛЕНО] v_reload_start = {current_vars['v_reload_start']}")
        
        if 'v_reload_start' in current_vars and 'v_hist_start' in current_vars:
            print(f"  [ИНФО] v_reload_start будет проверен на >= v_hist_start в SQL")
        
        print("\n[DEBUG] Последовательное выполнение блоков:")
        
        last_sql_block_index = -1
        
        # Очищаем кэш планов для нового запуска
        self.plan_cache = {}
        
        for idx, block in enumerate(self.blocks):
            block_type = self.block_types[idx] if idx < len(self.block_types) else 'UNKNOWN'
            
            # Пропускаем нетекстовые блоки для ускорения
            if block_type in ['DECLARE', 'END', 'OTHER', 'CREATE', 'RETURN']:
                continue
            
            print(f"\n--- Блок {idx+1} [{block_type}] ---")
            
            if ':=' in block:
                block_vars = self._extract_assignments_from_block_recursive(block)
                
                if block_vars:
                    print(f"  Найдены присваивания в блоке: {', '.join(block_vars.keys())}")
                    
                    for var_name, expr in block_vars.items():
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
                        current_vars[var_name] = 'NULL'
                        print(f"    📍 {var_name} = (из SELECT INTO)")
            
            if block_parser.is_executable_sql(block_type):
                block_with_vars = block
                for var_name, var_value in current_vars.items():
                    if var_value != 'NULL' and var_value != '':
                        pattern = r'\b' + re.escape(var_name) + r'\b'
                        block_with_vars = re.sub(pattern, str(var_value), block_with_vars)
                
                clean_sql = self._clean_sql_for_explain(block_with_vars)
                if clean_sql:
                    print(f"  SQL (первые 100): {clean_sql[:100]}...")
                    
                    tables_in_block = self._extract_objects_from_sql(clean_sql)
                    print(f"  📋 Таблицы в блоке: {[f'{sch}.{tbl}' for sch, tbl in tables_in_block]}")
                    
                    # Используем кэш для планов
                    cache_key = hashlib.md5(clean_sql.encode()).hexdigest()
                    if cache_key in self.plan_cache:
                        plan_json = self.plan_cache[cache_key]
                        print(f"  🔄 Использован кэшированный план")
                    else:
                        plan_json = self._get_plan_for_block(clean_sql)
                        if plan_json:
                            self.plan_cache[cache_key] = plan_json
                    
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
                        
                        self.block_results.append({
                            'index': idx+1,
                            'type': block_type,
                            'category': block_parser.get_block_category(block_type),
                            'sql_preview': clean_sql[:200] + '...',
                            'plan': adjusted_plan,
                            'load': block_load,
                            'tables': [f"{sch}.{tbl}" for sch, tbl in tables_in_block]
                        })
                        print(f"  ✅ Нагрузка блока: {block_load['max_memory_gb']:.3f} GB")
                        
                        last_sql_block_index = len(self.block_results) - 1
                    else:
                        print(f"  ❌ Не удалось получить план для SQL")
            
            if 'GET DIAGNOSTICS' in block.upper():
                diag_vars = self._extract_get_diagnostics(block)
                for var_name in diag_vars:
                    if last_sql_block_index >= 0 and self.block_results:
                        rows = self.block_results[last_sql_block_index]['load'].get('total_rows', 0)
                        current_vars[var_name] = str(rows)
                        print(f"    📊 GET DIAGNOSTICS {var_name} = {rows}")
        
        self.variables = current_vars
        
        total_load = self._calculate_total_load(self.block_results)
        top_blocks = self._get_top_blocks(self.block_results, 3)
        
        result = {
            'input_type': 'function',
            'function': self.func_name,
            'blocks_count': len(self.blocks),
            'analyzed_blocks': len(self.block_results),
            'total_memory_gb': total_load['total_memory_gb'],
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
                    'tables': b['tables']
                } for b in self.block_results
            ],
            'timestamp': datetime.now().isoformat()
        }
        
        self._print_detailed_report(result)
        return result

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
        
        # Используем версионированный кэш или создаем новый
        if not hasattr(self, 'versioned_plan_cache'):
            self.versioned_plan_cache = {}
        
        if versioned_cache_key not in self.versioned_plan_cache:
            self.versioned_plan_cache[versioned_cache_key] = {}
            print(f"🆕 Создан новый кэш планов для текущих размеров")
        
        current_cache = self.versioned_plan_cache[versioned_cache_key]
        
        # Для запроса анализируем каждый блок (CTE, основной запрос)
        for idx, block in enumerate(self.blocks):
            block_type = self.block_types[idx] if idx < len(self.block_types) else 'UNKNOWN'
            
            print(f"\n--- Блок {idx+1} [{block_type}] ---")
            
            if not block_parser.is_executable_sql(block_type):
                continue
            
            clean_sql = self._clean_sql_for_explain(block)
            if not clean_sql:
                continue
            
            print(f"  SQL (первые 100): {clean_sql[:100]}...")
            
            # Извлекаем таблицы в блоке
            tables_in_block = self._extract_objects_from_sql(clean_sql)
            print(f"  📋 Таблицы в блоке: {[f'{sch}.{tbl}' for sch, tbl in tables_in_block]}")
            
            # Используем версионированный кэш для планов
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
                # Улучшаем план с учётом временных таблиц
                enhanced_plan = self.temp_table_tracker.enhance_plan_with_temp_table_stats(
                    plan_json, self.discovered_tables
                )
                
                # Применяем пользовательские размеры
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
                
                # Вычисляем нагрузку
                block_load = plan_adjuster.compute_block_load(
                    adjusted_plan,
                    multipliers=self.multipliers,
                    segments=self.config.segments
                )
                
                self.block_results.append({
                    'index': idx+1,
                    'type': block_type,
                    'category': block_parser.get_block_category(block_type),
                    'sql_preview': clean_sql[:200] + '...',
                    'plan': adjusted_plan,
                    'load': block_load,
                    'tables': [f"{sch}.{tbl}" for sch, tbl in tables_in_block]
                })
                print(f"  ✅ Нагрузка блока: {block_load['max_memory_gb']:.3f} GB")
            else:
                print(f"  ❌ Не удалось получить план для SQL")
        
        # Формируем отчёт
        total_load = self._calculate_total_load(self.block_results)
        top_blocks = self._get_top_blocks(self.block_results, 3)
        
        result = {
            'input_type': 'query',
            'blocks_count': len(self.blocks),
            'analyzed_blocks': len(self.block_results),
            'total_memory_gb': total_load['total_memory_gb'],
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
                    'tables': b['tables']
                } for b in self.block_results
            ],
            'timestamp': datetime.now().isoformat()
        }
        
        self._print_detailed_report(result)
        return result


    def _calculate_total_load(self, block_results: List[Dict]) -> Dict:
        """Вычисляет суммарную нагрузку"""
        total_memory_gb = sum(b['load']['max_memory_gb'] for b in block_results)
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
        
        print(f"Всего блоков: {result['blocks_count']}, проанализировано: {result['analyzed_blocks']}")
        
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
        print(f"МАКСИМАЛЬНАЯ УТИЛИЗАЦИЯ: {result['max_utilization']:.1f}% RAM/сегмент")
        print(f"РИСК: {result['risk']}")
        print(f"ОЦЕНОЧНОЕ ВРЕМЯ ВЫПОЛНЕНИЯ: {result['estimated_time_sec']:.2f} сек")
        print("="*80)