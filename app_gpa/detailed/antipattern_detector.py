# -*- coding: utf-8 -*-
"""
Детектор антипаттернов SQL для оценки риска краша расчёта на скейле данных.
Паттерны оцениваются в контексте запроса; рост нагрузки масштабируется с размерами таблиц,
заданными пользователем (user_table_sizes). Возвращает найденные паттерны и рекомендации по хеджированию.

Множители ANTIPATTERN_LOAD_MULTIPLIERS основаны на бенчмарках: N+1 9–26x (Stack Insight),
CROSS JOIN экспоненциальный рост, коррелированный IN 3x+ на больших данных.
"""

import re
from typing import Dict, List, Any, Tuple


# Паттерны: (regex или проверка, название, описание, рекомендация по хеджированию)
_ANTIPATTERNS: List[Tuple[Any, str, str, str]] = [
    (
        lambda s: re.search(r'LATERAL\s*\([\s\S]*?ORDER\s+BY[\s\S]*?LIMIT\s+1\b', s, re.IGNORECASE),
        'LATERAL с ORDER BY + LIMIT 1',
        'Зависимый подзапрос выполняется для каждой строки внешней таблицы — N+1 нагрузка.',
        'Заменить на JOIN с агрегатом или оконной функцией; предварительно материализовать подзапрос.',
    ),
    (
        lambda s: re.search(r'\bCROSS\s+JOIN\b|FROM\s+\w+\s*,\s*\w+(?:\s|$)', s, re.IGNORECASE),
        'CROSS JOIN / декартово произведение',
        'Выходных строк = rows_A × rows_B. На скейле может взорваться до триллионов.',
        'Добавить явное условие JOIN; разбить на чанки по партициям; ограничить размер выборки.',
    ),
    (
        lambda s: re.search(r'WHERE\s+[^;]+IN\s*\(\s*SELECT\s+[^)]+WHERE\s+[^)]*\b\w+\.\w+\s*=', s, re.IGNORECASE | re.DOTALL),
        'Коррелированный подзапрос IN',
        'Подзапрос выполняется для каждой строки внешней таблицы.',
        'Переписать на JOIN или EXISTS; материализовать подзапрос во временную таблицу.',
    ),
    (
        lambda s: re.search(r'\bNOT\s+IN\s*\(\s*SELECT\b', s, re.IGNORECASE),
        'NOT IN (subquery)',
        'Часто выполняется как вложенный SubPlan; NULL в подзапросе даёт неожиданный результат.',
        'Заменить на NOT EXISTS или LEFT JOIN ... IS NULL.',
    ),
    (
        lambda s: re.search(r'\bUNION\b(?!\s+ALL)', s, re.IGNORECASE),
        'UNION без ALL',
        'Требует Sort + Unique для дедупликации — обрабатывает все строки.',
        'Использовать UNION ALL если дубликаты допустимы; фильтровать до UNION.',
    ),
    (
        lambda s: re.search(r'\bRECURSIVE\s+', s, re.IGNORECASE) and 'WITH' in s.upper(),
        'Recursive CTE',
        'При глубокой рекурсии или широком fan-out Plan Rows может взрываться.',
        'Ограничить глубину рекурсии (LIMIT depth); добавить индексы на join-колонки.',
    ),
    (
        lambda s: re.search(r'\bORDER\s+BY\b', s, re.IGNORECASE) and not re.search(r'\bLIMIT\s+\d+', s, re.IGNORECASE),
        'ORDER BY без LIMIT',
        'Полная сортировка всех строк; при больших объёмах — spill на диск.',
        'Добавить LIMIT если нужна выборка; фильтровать до сортировки.',
    ),
    (
        lambda s: re.search(r'\bSELECT\s+DISTINCT\b', s, re.IGNORECASE),
        'SELECT DISTINCT',
        'Sort или HashAggregate по всем входным строкам.',
        'Фильтровать до DISTINCT; рассмотреть GROUP BY вместо DISTINCT.',
    ),
    (
        lambda s: re.search(r'\bDISTINCT\s+ON\s*\(', s, re.IGNORECASE) and 'SELECT' in s.upper(),
        'DISTINCT ON в подзапросе',
        'PostgreSQL обрабатывает весь dataset перед фильтрацией.',
        'Вынести DISTINCT ON из подзапроса; использовать ROW_NUMBER() OVER (PARTITION BY ...).',
    ),
    (
        lambda s: re.search(r'date_trunc\s*\([^)]+\)\s*[=<>]|LOWER\s*\([^)]+\)\s*[=<>]|UPPER\s*\([^)]+\)\s*[=<>]', s, re.IGNORECASE),
        'Функции в условиях (non-SARGable)',
        'Блокирует использование индекса и pushdown — полный скан.',
        'Переписать: ts >= date_trunc(...) AND ts < ...; использовать expression index.',
    ),
    (
        lambda s: re.search(r'\bFROM\s+(\w+)\s+.*\bJOIN\s+.*\s+\1\b', s, re.IGNORECASE),
        'Self-join',
        'Таблица соединена сама с собой; Plan Rows может быть rows² при плохом селекторе. На скейле — квадратичный рост.',
        'Добавить индексы на join-колонки; фильтровать до join; рассмотреть оконные функции.',
    ),
    (
        lambda s: re.search(r'\bIN\s*\(\s*(?!\s*SELECT)[^)]{150,}\s*\)', s, re.IGNORECASE | re.DOTALL) or (len(re.findall(r'\bOR\b', s, re.IGNORECASE)) >= 8),
        'Большие IN / много OR',
        'Длинный IN (val1, val2, ...) или множество OR в WHERE ухудшают производительность; на скейле план может быть неоптимален.',
        'Заменить на JOIN с временной таблицей; использовать IN (SELECT ...) вместо IN (val1, val2, ...).',
    ),
    (
        lambda s: re.search(r'\bLIMIT\s+\d+\b', s, re.IGNORECASE) and re.search(r'\bORDER\s+BY\b', s, re.IGNORECASE),
        'ORDER BY + LIMIT',
        'Планировщик может выбрать full index scan в неправильном направлении; при больших таблицах сканирует миллионы строк.',
        'Составной индекс (filter_cols, order_col); фильтровать до сортировки.',
    ),
]


def detect_antipatterns(sql: str) -> List[Dict[str, str]]:
    """
    Сканирует SQL на антипаттерны. Возвращает список {pattern, reason, hedge, match_text}.
    match_text — подстрока SQL, соответствующая антипаттерну (для подсветки).
    """
    if not sql or not sql.strip():
        return []
    sql_norm = ' '.join(sql.split())
    found: List[Dict[str, str]] = []
    seen: set = set()
    for check, name, reason, hedge in _ANTIPATTERNS:
        if name in seen:
            continue
        try:
            match_text = name
            if callable(check):
                m = check(sql_norm)
                if m:
                    match_text = m.group(0) if hasattr(m, 'group') else name
                    found.append({'pattern': name, 'reason': reason, 'hedge': hedge, 'match_text': match_text})
                    seen.add(name)
            elif isinstance(check, re.Pattern):
                m = check.search(sql_norm)
                if m:
                    match_text = m.group(0)
                    found.append({'pattern': name, 'reason': reason, 'hedge': hedge, 'match_text': match_text})
                    seen.add(name)
        except Exception:
            pass
    return found


def get_hedge_recommendations(anti_patterns: List[Dict[str, str]]) -> List[str]:
    """
    Собирает уникальные рекомендации по хеджированию из списка антипаттернов.
    """
    hedges: List[str] = []
    seen: set = set()
    for ap in anti_patterns:
        h = ap.get('hedge', '').strip()
        if h and h not in seen:
            seen.add(h)
            hedges.append(h)
    return hedges


# Множители нагрузки для антипаттернов (пристрастная оценка на скейле данных)
ANTIPATTERN_LOAD_MULTIPLIERS = {
    'LATERAL с ORDER BY + LIMIT 1': 2.5,
    'CROSS JOIN / декартово произведение': 2.5,
    'Коррелированный подзапрос IN': 2.0,
    'NOT IN (subquery)': 1.6,
    'UNION без ALL': 1.6,
    'Recursive CTE': 1.8,
    'ORDER BY без LIMIT': 1.5,
    'SELECT DISTINCT': 1.5,
    'DISTINCT ON в подзапросе': 1.6,
    'Функции в условиях (non-SARGable)': 1.4,
    'Self-join': 2.0,
    'Большие IN / много OR': 1.5,
    'ORDER BY + LIMIT': 1.4,
}
DEFAULT_ANTIPATTERN_MULTIPLIER = 1.4  # если паттерн не в списке

# Пороги для скейл-фактора (при большой нагрузке блока множитель дополнительно растёт)
SCALE_FACTOR_THRESHOLDS = [(1.0, 1.15), (5.0, 1.25), (10.0, 1.35), (20.0, 1.5)]


def get_antipattern_load_multiplier(
    anti_patterns: List[Dict[str, str]],
    block_max_memory_gb: float = 0.0,
) -> float:
    """
    Возвращает множитель нагрузки для блока с антипаттернами (1.0 = без изменений).
    На скейле данных (block_max_memory_gb > 1 GB) множитель дополнительно увеличивается.
    """
    if not anti_patterns:
        return 1.0
    mults = [ANTIPATTERN_LOAD_MULTIPLIERS.get(ap.get('pattern', ''), DEFAULT_ANTIPATTERN_MULTIPLIER) for ap in anti_patterns]
    base_mult = max(mults) if mults else 1.0
    # Дополнительный скейл-фактор при большой нагрузке блока
    scale = 1.0
    for threshold_gb, scale_val in SCALE_FACTOR_THRESHOLDS:
        if block_max_memory_gb >= threshold_gb:
            scale = scale_val
    return base_mult * scale


# Общие рекомендации по хеджированию краша расчёта на скейле
GENERAL_HEDGE_RECOMMENDATIONS = [
    'Все паттерны оценивать в контексте запроса: рост нагрузки масштабируется с user_table_sizes.',
    'Ограничить размер входных данных: фильтр по партиции/дате, LIMIT на тестовых прогонах.',
    'Увеличить work_mem для Sort/Hash Join; мониторить spill на диск (Batches > 1 в EXPLAIN).',
    'Разбить тяжёлый блок на чанки: обрабатывать по партициям или батчам.',
    'Предварительно материализовать подзапросы во временные таблицы с индексами.',
    'Добавить statement_timeout для защиты от зависаний.',
    'Проверить статистику: ANALYZE после массовых загрузок; расширенная статистика при многоколоночных фильтрах.',
]
