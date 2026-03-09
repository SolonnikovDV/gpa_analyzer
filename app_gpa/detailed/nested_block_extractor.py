"""
Модуль для извлечения вложенных SQL блоков из BEGIN...END конструкций PL/pgSQL.
Позволяет найти все SQL операторы внутри функции, включая те что находятся в условиях и циклах.
"""

import re
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass


@dataclass
class SqlBlock:
    """Информация о найденном SQL блоке"""
    sql: str
    block_type: str  # SELECT, INSERT, UPDATE, DELETE, WITH, etc.
    line_number: int
    block_context: str  # BEGIN, IF, LOOP, etc.
    parent_block: Optional['SqlBlock'] = None
    available_variables: Set[str] = None  # Переменные доступные в этом блоке
    
    def __post_init__(self):
        if self.available_variables is None:
            self.available_variables = set()


class NestedBlockExtractor:
    """
    Извлекает вложенные SQL блоки из PL/pgSQL кода.
    
    Особенности:
    - Обрабатывает BEGIN...END блоки
    - Обрабатывает IF...THEN...ELSE...END IF
    - Обрабатывает циклы (FOR, WHILE, LOOP)
    - Отслеживает доступные переменные для каждого блока
    - Обрабатывает EXCEPTION блоки
    """
    
    def __init__(self):
        self.sql_blocks: List[SqlBlock] = []
        self.current_depth = 0
        self.current_variables: Set[str] = set()
    
    def extract_blocks(self, text: str) -> List[SqlBlock]:
        """
        Главный метод для извлечения всех SQL блоков из текста.
        """
        self.sql_blocks = []
        self.current_depth = 0
        self.current_variables = set()
        
        lines = text.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Пропускаем комментарии и пустые строки
            if not stripped or stripped.startswith('--') or stripped.startswith('/*'):
                i += 1
                continue
            
            # Обработка DECLARE блока (сбор переменных)
            if stripped.upper().startswith('DECLARE'):
                i = self._process_declare_block(lines, i)
                continue
            
            # Обработка BEGIN блока
            if stripped.upper().startswith('BEGIN'):
                i = self._process_begin_block(lines, i, parent_context='FUNCTION')
                continue
            
            # Обработка IF блока
            if stripped.upper().startswith('IF'):
                i = self._process_if_block(lines, i, parent_context='IF')
                continue
            
            # Обработка LOOP блока
            if re.match(r'^\s*(FOR|WHILE|LOOP)\s+', stripped, re.IGNORECASE):
                i = self._process_loop_block(lines, i)
                continue
            
            # Обработка отдельных SQL операторов
            if self._is_sql_statement(stripped):
                sql, next_i = self._extract_statement(lines, i)
                if sql:
                    block_type = self._classify_sql(sql)
                    sql_block = SqlBlock(
                        sql=sql,
                        block_type=block_type,
                        line_number=i + 1,
                        block_context='MAIN',
                        available_variables=self.current_variables.copy()
                    )
                    self.sql_blocks.append(sql_block)
                i = next_i
                continue
            
            i += 1
        
        return self.sql_blocks
    
    def _process_declare_block(self, lines: List[str], start_idx: int) -> int:
        """
        Обрабатывает DECLARE блок и собирает имена переменных.
        """
        i = start_idx
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Конец DECLARE блока
            if stripped.upper().startswith('BEGIN'):
                return i
            
            # Извлекаем имена переменных
            # Формат: name [CONSTANT] type [DEFAULT|:= value];
            var_match = re.match(r'^\s*([a-z_][a-z0-9_]*)\s+', stripped, re.IGNORECASE)
            if var_match:
                var_name = var_match.group(1).lower()
                self.current_variables.add(var_name)
            
            i += 1
        
        return i
    
    def _process_begin_block(self, lines: List[str], start_idx: int, parent_context: str = 'BEGIN') -> int:
        """
        Рекурсивно обрабатывает BEGIN...END блок.
        """
        i = start_idx + 1
        depth = 1
        
        while i < len(lines) and depth > 0:
            line = lines[i]
            stripped = line.strip()
            
            # Увеличиваем глубину вложенности
            if re.match(r'^\s*BEGIN\s*', stripped, re.IGNORECASE):
                depth += 1
            
            # Уменьшаем глубину вложенности
            if re.match(r'^\s*END\s*', stripped, re.IGNORECASE):
                depth -= 1
                if depth == 0:
                    return i + 1
            
            # Обработка IF внутри BEGIN
            if stripped.upper().startswith('IF'):
                i = self._process_if_block(lines, i, parent_context='IF')
                continue
            
            # Обработка LOOP внутри BEGIN
            if re.match(r'^\s*(FOR|WHILE|LOOP)\s+', stripped, re.IGNORECASE):
                i = self._process_loop_block(lines, i)
                continue
            
            # Обработка EXCEPTION
            if stripped.upper().startswith('EXCEPTION'):
                i = self._process_exception_block(lines, i)
                continue
            
            # Извлечение SQL операторов
            if self._is_sql_statement(stripped):
                sql, next_i = self._extract_statement(lines, i)
                if sql:
                    block_type = self._classify_sql(sql)
                    sql_block = SqlBlock(
                        sql=sql,
                        block_type=block_type,
                        line_number=i + 1,
                        block_context=parent_context,
                        available_variables=self.current_variables.copy()
                    )
                    self.sql_blocks.append(sql_block)
                i = next_i
                continue
            
            # Извлечение присваиваний переменных
            if ':=' in stripped:
                self._extract_assignment_variables(stripped)
            
            i += 1
        
        return i
    
    def _process_if_block(self, lines: List[str], start_idx: int, parent_context: str = 'IF') -> int:
        """
        Обрабатывает IF...THEN...ELSE...END IF блок.
        """
        i = start_idx + 1
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Конец IF блока
            if stripped.upper().startswith('END IF'):
                return i + 1
            
            # ELSE IF или ELSIF
            if re.match(r'^\s*(ELSE\s+)?IF\s+', stripped, re.IGNORECASE):
                pass  # Продолжаем обработку
            
            # ELSE
            if stripped.upper().startswith('ELSE'):
                i += 1
                continue
            
            # BEGIN внутри IF
            if stripped.upper().startswith('BEGIN'):
                i = self._process_begin_block(lines, i, parent_context='IF')
                continue
            
            # LOOP внутри IF
            if re.match(r'^\s*(FOR|WHILE|LOOP)\s+', stripped, re.IGNORECASE):
                i = self._process_loop_block(lines, i)
                continue
            
            # SQL операторы
            if self._is_sql_statement(stripped):
                sql, next_i = self._extract_statement(lines, i)
                if sql:
                    block_type = self._classify_sql(sql)
                    sql_block = SqlBlock(
                        sql=sql,
                        block_type=block_type,
                        line_number=i + 1,
                        block_context=parent_context,
                        available_variables=self.current_variables.copy()
                    )
                    self.sql_blocks.append(sql_block)
                i = next_i
                continue
            
            i += 1
        
        return i
    
    def _process_loop_block(self, lines: List[str], start_idx: int) -> int:
        """
        Обрабатывает LOOP/FOR/WHILE блоки.
        """
        i = start_idx + 1
        loop_type = lines[start_idx].strip().split()[0].upper()
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Конец цикла
            if stripped.upper().startswith('END LOOP'):
                return i + 1
            
            # BEGIN внутри цикла
            if stripped.upper().startswith('BEGIN'):
                i = self._process_begin_block(lines, i, parent_context=loop_type)
                continue
            
            # SQL операторы
            if self._is_sql_statement(stripped):
                sql, next_i = self._extract_statement(lines, i)
                if sql:
                    block_type = self._classify_sql(sql)
                    sql_block = SqlBlock(
                        sql=sql,
                        block_type=block_type,
                        line_number=i + 1,
                        block_context=loop_type,
                        available_variables=self.current_variables.copy()
                    )
                    self.sql_blocks.append(sql_block)
                i = next_i
                continue
            
            i += 1
        
        return i
    
    def _process_exception_block(self, lines: List[str], start_idx: int) -> int:
        """
        Обрабатывает EXCEPTION блок.
        """
        i = start_idx + 1
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Конец EXCEPTION (обычно END блока после него)
            if stripped.upper().startswith('END'):
                return i
            
            # SQL операторы в EXCEPTION
            if self._is_sql_statement(stripped):
                sql, next_i = self._extract_statement(lines, i)
                if sql:
                    block_type = self._classify_sql(sql)
                    sql_block = SqlBlock(
                        sql=sql,
                        block_type=block_type,
                        line_number=i + 1,
                        block_context='EXCEPTION',
                        available_variables=self.current_variables.copy()
                    )
                    self.sql_blocks.append(sql_block)
                i = next_i
                continue
            
            i += 1
        
        return i
    
    def _extract_statement(self, lines: List[str], start_idx: int) -> Tuple[Optional[str], int]:
        """
        Извлекает SQL оператор, начинающийся с start_idx.
        Возвращает (sql_statement, next_line_index).
        """
        i = start_idx
        current = []
        in_string = False
        in_dollar = False
        dollar_quote = None
        
        while i < len(lines):
            line = lines[i]
            
            j = 0
            while j < len(line):
                ch = line[j]
                
                # Обработка доллар-кавычек
                if ch == '$' and not in_string:
                    if not in_dollar:
                        # Начало доллар-кавычки
                        k = j + 1
                        while k < len(line) and (line[k].isalnum() or line[k] == '_'):
                            k += 1
                        if k < len(line) and line[k] == '$':
                            dollar_quote = line[j:k+1]
                            in_dollar = True
                            j = k
                    else:
                        # Проверка конца доллар-кавычки
                        if line[j:j+len(dollar_quote)] == dollar_quote:
                            in_dollar = False
                            dollar_quote = None
                            j += len(dollar_quote) - 1
                
                # Обработка обычных кавычек
                if ch == "'" and not in_dollar:
                    in_string = not in_string
                
                current.append(ch)
                
                # Конец оператора
                if ch == ';' and not in_string and not in_dollar:
                    stmt = ''.join(current).strip()
                    return (stmt, i + 1)
                
                j += 1
            
            current.append('\n')
            i += 1
        
        if current:
            stmt = ''.join(current).strip()
            if stmt and stmt != ';':
                return (stmt, i)
        
        return (None, i)
    
    def _is_sql_statement(self, line: str) -> bool:
        """
        Определяет, является ли строка началом SQL оператора.
        """
        tokens = line.upper().split()
        if not tokens:
            return False
        
        first_token = tokens[0]
        
        sql_starts = [
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'WITH',
            'CREATE', 'DROP', 'ALTER', 'TRUNCATE',
            'ANALYZE', 'VACUUM', 'EXECUTE', 'PERFORM',
            'COPY'
        ]
        
        return first_token in sql_starts
    
    def _classify_sql(self, sql: str) -> str:
        """
        Классифицирует SQL оператор по типу.
        """
        sql_upper = sql.strip().upper()
        
        if sql_upper.startswith('SELECT'):
            return 'SELECT'
        elif sql_upper.startswith('INSERT'):
            return 'INSERT'
        elif sql_upper.startswith('UPDATE'):
            return 'UPDATE'
        elif sql_upper.startswith('DELETE'):
            return 'DELETE'
        elif sql_upper.startswith('WITH'):
            return 'WITH'
        elif sql_upper.startswith('CREATE'):
            return 'CREATE'
        elif sql_upper.startswith('DROP'):
            return 'DROP'
        elif sql_upper.startswith('ALTER'):
            return 'ALTER'
        elif sql_upper.startswith('TRUNCATE'):
            return 'TRUNCATE'
        elif sql_upper.startswith('ANALYZE'):
            return 'ANALYZE'
        elif sql_upper.startswith('VACUUM'):
            return 'VACUUM'
        elif sql_upper.startswith('COPY'):
            return 'COPY'
        else:
            return 'OTHER'
    
    def _extract_assignment_variables(self, line: str) -> None:
        """
        Извлекает переменные из левой части присваивания (:=).
        """
        if ':=' in line:
            parts = line.split(':=')
            if parts:
                var_names = re.findall(r'\b([a-z_][a-z0-9_]*)\b', parts[0], re.IGNORECASE)
                for var_name in var_names:
                    self.current_variables.add(var_name.lower())


def extract_nested_sql_blocks(text: str) -> List[SqlBlock]:
    """
    Удобная функция для извлечения всех вложенных SQL блоков.
    """
    extractor = NestedBlockExtractor()
    return extractor.extract_blocks(text)
