"""
Модуль для отслеживания происхождения данных временных таблиц.
Позволяет определить, от каких физических таблиц/представлений наследуют данные временные таблицы.
"""

import re
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field


@dataclass
class TempTableOrigin:
    """Информация о происхождении временной таблицы"""
    table_name: str
    source_tables: Set[Tuple[str, str]]  # физические таблицы-источники
    source_views: Set[Tuple[str, str]]   # представления-источники
    query_type: str                       # 'SELECT', 'INSERT INTO ... SELECT', и т.д.
    sql_preview: str
    estimated_rows: int = 0
    estimated_size_gb: float = 0.0
    avg_row_size_bytes: float = 0.0
    column_count: int = 0
    inheritance_chain: List[str] = field(default_factory=list)  # цепочка наследования


class TempTableTracker:
    """
    Отслеживает создание временных таблиц и их зависимость от физических таблиц/представлений.
    Позволяет в дальнейшем применять характеристики источников к запросам с временными таблицами.
    """
    
    def __init__(self):
        self.temp_tables: Dict[str, TempTableOrigin] = {}  # имя -> информация о происхождении
        self.temp_table_creation_order: List[str] = []     # порядок создания для разрешения зависимостей
        
    def extract_temp_table_from_sql(self, sql: str) -> Optional[Tuple[str, str]]:
        """
        Извлекает имя временной таблицы из CREATE TEMP TABLE или INSERT INTO ... SELECT.
        Возвращает (table_name, query_type) или None.
        """
        sql_upper = sql.upper()
        
        # CREATE TEMP TABLE имя AS ...
        create_temp_match = re.search(r'CREATE\s+TEMP(?:ORARY)?\s+TABLE\s+(\w+)', sql_upper, re.IGNORECASE)
        if create_temp_match:
            return (create_temp_match.group(1).lower(), 'CREATE_TEMP_AS')
        
        # CREATE TABLE имя (как временная, если в temp_tables)
        create_table_match = re.search(r'CREATE\s+TABLE\s+(\w+)', sql_upper, re.IGNORECASE)
        if create_table_match:
            table_name = create_table_match.group(1).lower()
            if table_name in self.temp_tables or 'TEMP' in sql_upper:
                return (table_name, 'CREATE_TABLE')
        
        # INSERT INTO temp_table SELECT ...
        insert_temp_match = re.search(r'INSERT\s+INTO\s+(\w+)\s+SELECT', sql_upper, re.IGNORECASE)
        if insert_temp_match:
            table_name = insert_temp_match.group(1).lower()
            if table_name in self.temp_tables:
                return (table_name, 'INSERT_INTO_SELECT')
        
        return None
    
    def analyze_temp_table_origin(self, sql: str, temp_table_name: str, 
                                  physical_tables: Set[Tuple[str, str]],
                                  views: Set[Tuple[str, str]],
                                  view_definitions: Dict[Tuple[str, str], str]) -> TempTableOrigin:
        """
        Анализирует происхождение данных временной таблицы.
        """
        source_tables = set()
        source_views = set()
        
        # Извлекаем все объекты из SQL
        from block_parser import extract_objects_from_sql
        objects = extract_objects_from_sql(sql)
        
        for schema, obj_name in objects:
            obj_key = (schema.lower(), obj_name.lower())
            if obj_key in physical_tables:
                source_tables.add(obj_key)
            elif obj_key in views:
                source_views.add(obj_key)
                # Рекурсивно раскрываем представление
                if obj_key in view_definitions:
                    view_sql = view_definitions[obj_key]
                    view_objects = extract_objects_from_sql(view_sql)
                    for v_schema, v_name in view_objects:
                        v_key = (v_schema.lower(), v_name.lower())
                        if v_key in physical_tables:
                            source_tables.add(v_key)
        
        # Строим цепочку наследования
        inheritance_chain = [temp_table_name]
        for view in source_views:
            inheritance_chain.append(f"{view[0]}.{view[1]}")
        for table in source_tables:
            inheritance_chain.append(f"{table[0]}.{table[1]}")
        
        return TempTableOrigin(
            table_name=temp_table_name,
            source_tables=source_tables,
            source_views=source_views,
            query_type='CREATE_TEMP_AS' if 'CREATE' in sql.upper() else 'INSERT_INTO_SELECT',
            sql_preview=sql[:200],
            inheritance_chain=inheritance_chain
        )
    
    def register_temp_table(self, sql: str, temp_table_name: str,
                           physical_tables: Set[Tuple[str, str]],
                           views: Set[Tuple[str, str]],
                           view_definitions: Dict[Tuple[str, str], str]) -> None:
        """
        Регистрирует создание временной таблицы и определяет её происхождение.
        """
        if temp_table_name not in self.temp_tables:
            origin = self.analyze_temp_table_origin(
                sql, temp_table_name, physical_tables, views, view_definitions
            )
            self.temp_tables[temp_table_name] = origin
            self.temp_table_creation_order.append(temp_table_name)
            print(f"  📊 Зарегистрирована временная таблица: {temp_table_name}")
            if origin.source_tables:
                print(f"    Источники (таблицы): {', '.join([f'{s}.{t}' for s, t in origin.source_tables])}")
            if origin.source_views:
                print(f"    Источники (представления): {', '.join([f'{s}.{t}' for s, t in origin.source_views])}")
    
    def get_table_characteristics(self, table_name: str, 
                                 physical_table_stats: Dict[str, Dict]) -> Dict[str, Any]:
        """
        Возвращает характеристики таблицы (физической или временной).
        Для временной таблицы возвращает агрегированные характеристики источников.
        """
        table_name_lower = table_name.lower()
        
        # Если это физическая таблица
        for full_name, stats in physical_table_stats.items():
            if full_name.endswith('.' + table_name_lower) or full_name == table_name_lower:
                return {
                    'type': 'physical',
                    'rows': stats.get('current_rows', 0),
                    'size_gb': stats.get('size_gb', 0),
                    'avg_row_size': stats.get('avg_row_size_bytes', 0),
                    'columns': stats.get('columns', 0)
                }
        
        # Если это временная таблица
        if table_name_lower in self.temp_tables:
            origin = self.temp_tables[table_name_lower]
            
            # Если есть прямые источники-таблицы, берём их характеристики
            if origin.source_tables:
                total_rows = 0
                total_size = 0
                total_columns = 0
                count = 0
                
                for schema, table in origin.source_tables:
                    full_name = f"{schema}.{table}"
                    if full_name in physical_table_stats:
                        stats = physical_table_stats[full_name]
                        total_rows += stats.get('current_rows', 0)
                        total_size += stats.get('size_gb', 0)
                        total_columns += stats.get('columns', 0)
                        count += 1
                
                if count > 0:
                    return {
                        'type': 'temp',
                        'rows': total_rows,
                        'size_gb': total_size,
                        'avg_row_size': total_size * 1024**3 / total_rows if total_rows > 0 else 0,
                        'columns': total_columns // count,  # среднее количество колонок
                        'origin': origin.inheritance_chain
                    }
            
            # Если есть только представления, пытаемся получить через них
            elif origin.source_views:
                # Рекурсивно пытаемся найти физические таблицы через представления
                # (упрощённо - возвращаем заглушку)
                return {
                    'type': 'temp_view_based',
                    'rows': 1000000,  # заглушка
                    'size_gb': 1.0,   # заглушка
                    'avg_row_size': 100,  # заглушка
                    'columns': 10,     # заглушка
                    'origin': origin.inheritance_chain
                }
        
        # Таблица не найдена
        return {
            'type': 'unknown',
            'rows': 0,
            'size_gb': 0,
            'avg_row_size': 0,
            'columns': 0
        }
    
    def enhance_plan_with_temp_table_stats(self, plan: dict, 
                                          physical_table_stats: Dict[str, Dict]) -> dict:
        """
        Улучшает план запроса, добавляя информацию о временных таблицах.
        Модифицирует оценки строк для узлов, работающих с временными таблицами.
        """
        def process_node(node: dict):
            if 'Relation Name' in node:
                rel_name = node['Relation Name'].lower()
                
                # Проверяем, не временная ли это таблица
                if rel_name in self.temp_tables:
                    chars = self.get_table_characteristics(rel_name, physical_table_stats)
                    if chars['rows'] > 0:
                        # Корректируем оценку строк
                        node['Plan Rows'] = chars['rows']
                        # Добавляем мета-информацию
                        node['Temp Table Origin'] = chars.get('origin', [])
                        node['Estimated from Source'] = True
                        print(f"    📊 Корректировка временной таблицы {rel_name}: {chars['rows']} строк")
            
            # Рекурсивно обрабатываем дочерние узлы
            if 'Plans' in node:
                for child in node['Plans']:
                    process_node(child)
        
        import copy
        enhanced_plan = copy.deepcopy(plan)
        process_node(enhanced_plan)
        return enhanced_plan