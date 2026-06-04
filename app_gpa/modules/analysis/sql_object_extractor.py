# ====================================================================
# Файл: detailed/sql_object_extractor.py (исправленная версия с улучшенным обходом)
# ====================================================================
"""
Модуль для извлечения объектов (таблиц, представлений) из SQL с использованием pglast.
"""

import re
from typing import List, Tuple, Set
import pglast
from pglast.ast import RangeVar, TruncateStmt, InsertStmt, DeleteStmt, UpdateStmt, SelectStmt, CopyStmt, Node


class SQLObjectExtractor:
    """
    Извлекает имена таблиц и представлений из SQL-запросов с использованием pglast.
    """
    
    @staticmethod
    def extract_objects(sql: str) -> List[Tuple[str, str]]:
        objects: Set[Tuple[str, str]] = set()
        clean_sql = re.sub(r'--.*?$', '', sql, flags=re.MULTILINE)
        clean_sql = re.sub(r'/\*.*?\*/', '', clean_sql, flags=re.DOTALL)
        if not clean_sql.strip():
            return []
        try:
            parsed = pglast.parse_sql(clean_sql)
            for stmt in parsed:
                nodes = SQLObjectExtractor._traverse_nodes(stmt)
                for node in nodes:
                    if isinstance(node, RangeVar):
                        schema = node.schemaname or 'public'
                        relname = node.relname
                        if relname:
                            objects.add((schema.lower(), relname.lower()))
                    if isinstance(node, TruncateStmt):
                        for rel in node.relations:
                            schema = rel.schemaname or 'public'
                            name = rel.relname
                            if name:
                                objects.add((schema.lower(), name.lower()))
                    if isinstance(node, CopyStmt):
                        if node.relation:
                            schema = node.relation.schemaname or 'public'
                            name = node.relation.relname
                            if name:
                                objects.add((schema.lower(), name.lower()))
                if hasattr(stmt, 'relation') and stmt.relation:
                    rel = stmt.relation
                    if hasattr(rel, 'relname'):
                        schema = getattr(rel, 'schemaname', 'public')
                        objects.add((schema.lower(), rel.relname.lower()))
        except Exception as e:
            print(f"  [pglast] Ошибка парсинга: {e}")
            objects.update(SQLObjectExtractor._fallback_extract(sql))
        return list(objects)

    @staticmethod
    def _traverse_nodes(root):
        """
        Рекурсивно обходит дерево узлов pglast, возвращая все узлы.
        Улучшенная версия, которая пытается извлечь все возможные дочерние узлы,
        даже если узел не имеет методов traverse/walk.
        """
        nodes = []
        stack = [root]
        seen = set()
        while stack:
            node = stack.pop()
            if id(node) in seen:
                continue
            seen.add(id(node))
            nodes.append(node)
            
            # Если узел имеет стандартные методы обхода
            if hasattr(node, 'traverse'):
                for child in node.traverse():
                    if child not in nodes:
                        stack.append(child)
            elif hasattr(node, 'walk'):
                for child in node.walk():
                    if child not in nodes:
                        stack.append(child)
            else:
                # Ручной обход: перебираем все атрибуты узла
                for attr_name in dir(node):
                    if attr_name.startswith('_'):
                        continue
                    try:
                        child = getattr(node, attr_name)
                    except Exception:
                        continue
                    if child is None:
                        continue
                    if isinstance(child, (list, tuple)):
                        for item in child:
                            if isinstance(item, Node):
                                stack.append(item)
                    elif isinstance(child, Node):
                        # Это узел AST pglast (используем базовый класс Node из pglast.ast)
                        stack.append(child)
        return nodes

    @staticmethod
    def _fallback_extract(sql: str) -> List[Tuple[str, str]]:
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

    @staticmethod
    def is_dml_statement(sql: str) -> bool:
        try:
            parsed = pglast.parse_sql(sql)
            for stmt in parsed:
                stmt_type = type(stmt).__name__
                if stmt_type in ['SelectStmt', 'InsertStmt', 'DeleteStmt', 'UpdateStmt', 'TruncateStmt']:
                    return True
                if hasattr(stmt, 'utility') and stmt.utility:
                    utility_type = type(stmt.utility).__name__
                    if utility_type in ['SelectStmt', 'InsertStmt', 'DeleteStmt', 'UpdateStmt', 'TruncateStmt']:
                        return True
            return False
        except:
            sql_upper = sql.strip().upper()
            dml_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'WITH']
            for kw in dml_keywords:
                if sql_upper.startswith(kw):
                    return True
            return False

    @staticmethod
    def extract_temp_tables(sql: str) -> List[str]:
        temp_tables = []
        try:
            parsed = pglast.parse_sql(sql)
            for stmt in parsed:
                for node in SQLObjectExtractor._traverse_nodes(stmt):
                    if isinstance(node, RangeVar) and node.relname:
                        pass
        except:
            pass
        pattern = r'CREATE\s+(?:TEMP|TEMPORARY)\s+TABLE\s+(\w+)'
        matches = re.findall(pattern, sql, re.IGNORECASE)
        for table_name in matches:
            temp_tables.append(table_name.lower())
        return temp_tables