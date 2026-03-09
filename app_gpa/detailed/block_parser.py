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
    'DECLARE': r'^\s*DECLARE\s+',
    'BEGIN': r'^\s*BEGIN\s+',
    'END': r'^\s*END\s+',
    'RETURN': r'^\s*RETURN\s+',
    'PERFORM': r'^\s*PERFORM\s+',
    'EXECUTE': r'^\s*EXECUTE\s+',
    'RAISE': r'^\s*RAISE\s+',
    'ASSERT': r'^\s*ASSERT\s+',
    'GET': r'^\s*GET\s+DIAGNOSTICS\s+',
    'IF': r'^\s*IF\s+',
    'CASE': r'^\s*CASE\s+',
    'LOOP': r'^\s*LOOP\s+',
    'WHILE': r'^\s*WHILE\s+',
    'FOR': r'^\s*FOR\s+',
    'EXIT': r'^\s*EXIT\s+',
    'CONTINUE': r'^\s*CONTINUE\s+',
    'NULL': r'^\s*NULL\s*;',
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


def split_plpgsql_blocks(text: str) -> List[str]:
    """
    Разделяет PL/pgSQL текст на отдельные операторы.
    Учитывает:
    - долларовые кавычки с тегами (например, $function$)
    - обычные кавычки ' и экранирование ''
    - комментарии -- и /* */
    - вложенные BEGIN/END и EXCEPTION блоки
    - точку с запятой как разделитель только на верхнем уровне (глубина блоков = 0)
    """
    statements = []
    current = []
    depth = 0
    in_string = False
    dollar_tag = None
    dollar_stack = []
    in_comment_line = False
    in_comment_block = False
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]
        next_ch = text[i+1] if i+1 < n else ''

        # ----- однострочные комментарии --
        if not in_string and not dollar_tag and not in_comment_block and ch == '-' and next_ch == '-':
            in_comment_line = True
            i += 2
            continue
        if in_comment_line:
            if ch == '\n':
                in_comment_line = False
                current.append(ch)
            i += 1
            continue

        # ----- блочные комментарии /* */
        if not in_string and not dollar_tag and not in_comment_line and ch == '/' and next_ch == '*':
            in_comment_block = True
            i += 2
            continue
        if in_comment_block:
            if ch == '*' and next_ch == '/':
                in_comment_block = False
                i += 2
                continue
            i += 1
            continue

        if in_comment_line or in_comment_block:
            i += 1
            continue

        # ----- обычные кавычки '
        if ch == "'" and not dollar_tag:
            in_string = not in_string
            current.append(ch)
            i += 1
            continue

        # ----- долларовые кавычки $tag$
        if ch == '$' and not in_string:
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == '_'):
                j += 1
            if j < n and text[j] == '$':
                tag = text[i:j+1]
                if not dollar_tag:
                    dollar_tag = tag
                    dollar_stack.append(tag)
                else:
                    if dollar_stack and dollar_stack[-1] == tag:
                        dollar_stack.pop()
                        dollar_tag = dollar_stack[-1] if dollar_stack else None
                current.append(tag)
                i = j
                i += 1
                continue

        if dollar_tag:
            current.append(ch)
            i += 1
            continue

        # ----- отслеживание глубины блоков BEGIN/END
        # Проверяем BEGIN (с учётом возможных пробелов)
        if not in_string:
            # Ищем BEGIN как отдельное слово
            if (ch.upper() == 'B' and 
                i+4 < n and 
                text[i:i+5].upper() == 'BEGIN' and 
                (i+5 == n or not text[i+5].isalnum())):
                depth += 1
                for k in range(5):
                    current.append(text[i+k])
                i += 5
                continue
            
            # Ищем END как отдельное слово
            if (ch.upper() == 'E' and 
                i+2 < n and 
                text[i:i+3].upper() == 'END' and 
                (i+3 == n or not text[i+3].isalnum())):
                depth -= 1
                for k in range(3):
                    current.append(text[i+k])
                i += 3
                continue
            
            # Ищем EXCEPTION
            if (ch.upper() == 'E' and 
                i+8 < n and 
                text[i:i+9].upper() == 'EXCEPTION' and 
                (i+9 == n or not text[i+9].isalnum())):
                for k in range(9):
                    current.append(text[i+k])
                i += 9
                continue

        current.append(ch)

        # разделение по точке с запятой на верхнем уровне
        if ch == ';' and depth == 0 and not in_string and not dollar_tag:
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []

        i += 1

    if current:
        stmt = ''.join(current).strip()
        if stmt:
            statements.append(stmt)

    return statements


def classify_block(sql: str) -> str:
    """
    Определяет тип SQL-блока по паттернам.
    Возвращает один из ключей из SQL_PATTERNS или 'OTHER'.
    """
    if not sql or not sql.strip():
        return 'OTHER'
    
    sql_upper = sql.strip().upper()
    
    # Сначала проверяем самые специфичные паттерны
    # CREATE TEMP TABLE
    if re.match(r'^\s*CREATE\s+(?:TEMP|TEMPORARY)\s+TABLE', sql_upper, re.IGNORECASE):
        return 'CREATE_TEMP'
    
    # CREATE TABLE
    if re.match(r'^\s*CREATE\s+TABLE', sql_upper, re.IGNORECASE):
        return 'CREATE'
    
    # INSERT
    if re.match(r'^\s*INSERT\s+INTO', sql_upper, re.IGNORECASE):
        return 'INSERT'
    
    # UPDATE
    if re.match(r'^\s*UPDATE', sql_upper, re.IGNORECASE):
        return 'UPDATE'
    
    # DELETE
    if re.match(r'^\s*DELETE\s+FROM', sql_upper, re.IGNORECASE):
        return 'DELETE'
    
    # TRUNCATE
    if re.match(r'^\s*TRUNCATE', sql_upper, re.IGNORECASE):
        return 'TRUNCATE'
    
    # WITH (CTE)
    if re.match(r'^\s*WITH\s+', sql_upper, re.IGNORECASE):
        return 'WITH'
    
    # SELECT
    if re.match(r'^\s*SELECT\s+', sql_upper, re.IGNORECASE):
        return 'SELECT'
    
    # ANALYZE
    if re.match(r'^\s*ANALYZE', sql_upper, re.IGNORECASE):
        return 'ANALYZE'
    
    # VACUUM
    if re.match(r'^\s*VACUUM', sql_upper, re.IGNORECASE):
        return 'VACUUM'
    
    # ALTER
    if re.match(r'^\s*ALTER', sql_upper, re.IGNORECASE):
        return 'ALTER'
    
    # DROP
    if re.match(r'^\s*DROP', sql_upper, re.IGNORECASE):
        return 'DROP'
    
    # GRANT
    if re.match(r'^\s*GRANT', sql_upper, re.IGNORECASE):
        return 'GRANT'
    
    # REVOKE
    if re.match(r'^\s*REVOKE', sql_upper, re.IGNORECASE):
        return 'REVOKE'
    
    # COMMENT
    if re.match(r'^\s*COMMENT', sql_upper, re.IGNORECASE):
        return 'COMMENT'
    
    # PL/pgSQL конструкции
    if re.match(r'^\s*DECLARE\s+', sql_upper, re.IGNORECASE):
        return 'DECLARE'
    
    if re.match(r'^\s*BEGIN\s+', sql_upper, re.IGNORECASE):
        return 'BEGIN'
    
    if re.match(r'^\s*END\s+', sql_upper, re.IGNORECASE):
        return 'END'
    
    if re.match(r'^\s*RETURN\s+', sql_upper, re.IGNORECASE):
        return 'RETURN'
    
    if re.match(r'^\s*PERFORM\s+', sql_upper, re.IGNORECASE):
        return 'PERFORM'
    
    if re.match(r'^\s*EXECUTE\s+', sql_upper, re.IGNORECASE):
        return 'EXECUTE'
    
    if re.match(r'^\s*RAISE\s+', sql_upper, re.IGNORECASE):
        return 'RAISE'
    
    if re.match(r'^\s*ASSERT\s+', sql_upper, re.IGNORECASE):
        return 'ASSERT'
    
    if re.match(r'^\s*GET\s+DIAGNOSTICS', sql_upper, re.IGNORECASE):
        return 'GET'
    
    if re.match(r'^\s*IF\s+', sql_upper, re.IGNORECASE):
        return 'IF'
    
    if re.match(r'^\s*CASE\s+', sql_upper, re.IGNORECASE):
        return 'CASE'
    
    if re.match(r'^\s*LOOP\s+', sql_upper, re.IGNORECASE):
        return 'LOOP'
    
    if re.match(r'^\s*WHILE\s+', sql_upper, re.IGNORECASE):
        return 'WHILE'
    
    if re.match(r'^\s*FOR\s+', sql_upper, re.IGNORECASE):
        return 'FOR'
    
    if re.match(r'^\s*EXIT\s+', sql_upper, re.IGNORECASE):
        return 'EXIT'
    
    if re.match(r'^\s*CONTINUE\s+', sql_upper, re.IGNORECASE):
        return 'CONTINUE'
    
    if re.match(r'^\s*NULL\s*;', sql_upper, re.IGNORECASE):
        return 'NULL'
    
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
    # Пропускаем только DECLARE и RETURN — всё остальное анализируем
    return block_type not in ['DECLARE', 'RETURN']


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
        sql = re.sub(rf'\${i}\b', val, sql)
    return sql


def extract_temp_tables_from_ddl(ddl: str) -> Set[str]:
    """
    Извлекает имена временных таблиц из CREATE TEMP TABLE statements.
    """
    temp_tables = set()
    
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
                if len(match) == 2:
                    schema, table = match
                    tables.add((schema, table))
                else:
                    table = match[0]
                    if table.lower() in temp_tables:
                        tables.add((None, table))
                    else:
                        tables.add((default_schema, table))
            else:
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