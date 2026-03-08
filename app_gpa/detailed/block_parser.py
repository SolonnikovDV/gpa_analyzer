import re
from typing import List, Tuple, Optional, Set

# Паттерны для определения типов блоков
SQL_PATTERNS = {
    'WITH': r'^\s*WITH\s+',
    'SELECT': r'^\s*SELECT\s+',
    'INSERT': r'^\s*INSERT\s+INTO\s+',
    'UPDATE': r'^\s*UPDATE\s+',
    'DELETE': r'^\s*DELETE\s+FROM\s+',
    'TRUNCATE': r'^\s*TRUNCATE\s+',
    'ALTER': r'^\s*ALTER\s+',
    'DROP': r'^\s*DROP\s+',
    'CREATE': r'^\s*CREATE\s+',
    'CREATE_TEMP': r'^\s*CREATE\s+(?:TEMP|TEMPORARY)\s+TABLE\s+',
    'ANALYZE': r'^\s*ANALYZE\s+',
    'VACUUM': r'^\s*VACUUM\s+',
    'GRANT': r'^\s*GRANT\s+',
    'REVOKE': r'^\s*REVOKE\s+',
    'COMMENT': r'^\s*COMMENT\s+',
    'DECLARE': r'^\s*DECLARE\s+',  # PL/pgSQL
    'BEGIN': r'^\s*BEGIN\s+',      # PL/pgSQL
    'END': r'^\s*END\s+',          # PL/pgSQL
    'RETURN': r'^\s*RETURN\s+',    # PL/pgSQL
    'PERFORM': r'^\s*PERFORM\s+',  # PL/pgSQL
    'EXECUTE': r'^\s*EXECUTE\s+',  # PL/pgSQL
    'RAISE': r'^\s*RAISE\s+',      # PL/pgSQL
    'ASSERT': r'^\s*ASSERT\s+',    # PL/pgSQL
    'GET': r'^\s*GET\s+DIAGNOSTICS\s+',  # PL/pgSQL
    'IF': r'^\s*IF\s+',            # PL/pgSQL
    'CASE': r'^\s*CASE\s+',         # PL/pgSQL
    'LOOP': r'^\s*LOOP\s+',         # PL/pgSQL
    'WHILE': r'^\s*WHILE\s+',       # PL/pgSQL
    'FOR': r'^\s*FOR\s+',           # PL/pgSQL
    'EXIT': r'^\s*EXIT\s+',         # PL/pgSQL
    'CONTINUE': r'^\s*CONTINUE\s+', # PL/pgSQL
    'NULL': r'^\s*NULL\s*;',        # PL/pgSQL
}

# Группировка типов по категориям
BLOCK_CATEGORIES = {
    'DATA_MODIFICATION': ['INSERT', 'UPDATE', 'DELETE', 'TRUNCATE'],
    'DATA_QUERY': ['SELECT', 'WITH'],
    'DDL': ['CREATE', 'ALTER', 'DROP', 'CREATE_TEMP'],
    'MAINTENANCE': ['ANALYZE', 'VACUUM'],
    'PERMISSIONS': ['GRANT', 'REVOKE', 'COMMENT'],
    'PLPGSQL_CONTROL': ['DECLARE', 'BEGIN', 'END', 'IF', 'CASE', 'LOOP', 'WHILE', 'FOR', 'EXIT', 'CONTINUE'],
    'PLPGSQL_EXEC': ['RETURN', 'PERFORM', 'EXECUTE', 'RAISE', 'ASSERT', 'GET'],
    'PLPGSQL_OTHER': ['NULL'],
    'OTHER': []
}


def split_sql_blocks(sql_text: str) -> List[str]:
    """
    Разделяет SQL-текст на блоки по ';' вне кавычек и комментариев.
    """
    # Удаляем многострочные комментарии
    sql_text = re.sub(r'/\*.*?\*/', '', sql_text, flags=re.DOTALL)
    # Удаляем однострочные комментарии
    sql_text = re.sub(r'--.*$', '', sql_text, flags=re.MULTILINE)
    
    blocks = []
    current = []
    in_string = False
    in_dollar_string = False
    dollar_tag = ''
    escape = False
    
    i = 0
    while i < len(sql_text):
        ch = sql_text[i]
        
        # Обработка доллар-кавычек ($$...$$)
        if not in_string and not in_dollar_string and ch == '$' and i+1 < len(sql_text) and sql_text[i+1] == '$':
            in_dollar_string = True
            dollar_tag = '$$'
            current.append(ch)
            i += 1
            current.append(sql_text[i])
            i += 1
            continue
        elif in_dollar_string and ch == '$' and i+1 < len(sql_text) and sql_text[i+1] == '$':
            current.append(ch)
            i += 1
            current.append(sql_text[i])
            in_dollar_string = False
            dollar_tag = ''
            i += 1
            continue
        
        # Обработка обычных кавычек
        if ch == "'" and not escape and not in_dollar_string:
            in_string = not in_string
        elif ch == '\\' and in_string:
            escape = True
        else:
            escape = False
        
        # Разделение по точке с запятой
        if ch == ';' and not in_string and not in_dollar_string:
            block = ''.join(current).strip()
            if block:
                blocks.append(block)
            current = []
        else:
            current.append(ch)
        
        i += 1
    
    if current:
        block = ''.join(current).strip()
        if block:
            blocks.append(block)
    
    return blocks


def classify_block(sql: str) -> str:
    """
    Определяет тип SQL-блока по паттернам.
    Возвращает один из ключей из SQL_PATTERNS или 'OTHER'.
    """
    sql_upper = sql.strip().upper()
    
    # Проверяем паттерны в порядке приоритета
    for pattern_name, pattern in SQL_PATTERNS.items():
        if re.match(pattern, sql_upper, re.IGNORECASE):
            return pattern_name
    
    return 'OTHER'


def get_block_category(block_type: str) -> str:
    """
    Возвращает категорию блока.
    """
    for category, types in BLOCK_CATEGORIES.items():
        if block_type in types:
            return category
    return 'OTHER'


def is_executable_sql(block_type: str) -> bool:
    """
    Проверяет, является ли блок выполняемым SQL (можно сделать EXPLAIN).
    """
    executable_types = ['SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE', 'CREATE_TEMP']
    return block_type in executable_types


def clean_sql_for_explain(sql: str) -> str:
    """
    Очищает SQL от PL/pgSQL конструкций для выполнения EXPLAIN.
    """
    # Удаляем INTO переменные
    sql = re.sub(r'INTO\s+\w+', '', sql, flags=re.IGNORECASE)
    
    # Удаляем PERFORM
    if re.match(r'^\s*PERFORM\s+', sql, re.IGNORECASE):
        return ''
    
    # Удаляем RETURN
    if re.match(r'^\s*RETURN\s+', sql, re.IGNORECASE):
        return ''
    
    # Удаляем GET DIAGNOSTICS
    if re.match(r'^\s*GET\s+DIAGNOSTICS', sql, re.IGNORECASE):
        return ''
    
    return sql.strip()


def substitute_params(sql: str, params: List[str]) -> str:
    """
    Заменяет позиционные параметры $1, $2, ... на фактические значения.
    """
    for i, val in enumerate(params, start=1):
        # Заменяем только целые слова $1, $2 и т.д.
        sql = re.sub(rf'\${i}\b', val, sql)
    return sql


def extract_temp_tables_from_ddl(ddl: str) -> Set[str]:
    """
    Извлекает имена временных таблиц из CREATE TEMP TABLE statements.
    """
    temp_tables = set()
    
    # Паттерн для CREATE TEMP TABLE имя_таблицы
    pattern = r'CREATE\s+(?:TEMP|TEMPORARY)\s+TABLE\s+(\w+)'
    matches = re.findall(pattern, ddl, re.IGNORECASE)
    
    for table_name in matches:
        temp_tables.add(table_name.lower())
    
    return temp_tables


def extract_tables_from_block(sql: str, default_schema: str, temp_tables: Set[str] = None) -> List[Tuple[Optional[str], str]]:
    """
    Извлекает имена таблиц из SQL-блока.
    Возвращает список кортежей (schema, table), где schema может быть None для временных таблиц.
    """
    if temp_tables is None:
        temp_tables = set()
    
    tables = set()
    
    # Ищем schema.table или table после ключевых слов
    patterns = [
        r'(?:FROM|JOIN|UPDATE|INTO|USING)\s+([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]+)',
        r'(?:FROM|JOIN|UPDATE|INTO|USING)\s+([a-z_][a-z0-9_]+)\b',
        r'INSERT\s+INTO\s+([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]+)',
        r'INSERT\s+INTO\s+([a-z_][a-z0-9_]+)\b',
        r'TRUNCATE\s+([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]+)',
        r'TRUNCATE\s+([a-z_][a-z0-9_]+)\b',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, sql, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                if len(match) == 2:  # schema.table
                    schema, table = match
                    tables.add((schema, table))
                else:  # только table
                    table = match[0]
                    # Проверяем, не является ли таблица временной
                    if table.lower() in temp_tables:
                        tables.add((None, table))
                    else:
                        tables.add((default_schema, table))
            else:  # строка - только table
                table = match
                if table.lower() in temp_tables:
                    tables.add((None, table))
                else:
                    tables.add((default_schema, table))
    
    return list(tables)


def extract_objects_from_sql(sql: str) -> List[Tuple[str, str]]:
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