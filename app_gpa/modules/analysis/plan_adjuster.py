from typing import Dict, List, Optional, Any

# Множители операций
DEFAULT_MULTIPLIERS = {
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


def apply_user_sizes_to_plan(plan: dict, user_table_sizes: Dict[str, int], view_to_tables_map: Dict[str, List[str]] = None, segments: int = 120) -> dict:
    """
    Применяет пользовательские размеры таблиц к плану.
    view_to_tables_map: словарь {представление: [физические_таблицы]}
    """
    import copy
    plan_copy = copy.deepcopy(plan)
    
    print("  📊 Применение пользовательских размеров:")
    
    # Если нет пользовательских размеров, выходим
    if not user_table_sizes:
        print("    Нет пользовательских размеров для применения")
        return plan_copy
    
    # Выводим все доступные пользовательские размеры для отладки
    print(f"    Доступные размеры: {list(user_table_sizes.keys())}")
    
    # Маппинг представлений: {view: [физические_таблицы]} — нужен когда план ссылается на view, а размеры заданы для базовых таблиц
    if view_to_tables_map:
        print(f"    Маппинг представлений (view → физические таблицы): {view_to_tables_map}")
    else:
        print(f"    Маппинг представлений: нет (режим без БД — сопоставление по имени таблицы/представления)")
    
    def adjust_node(node: dict):
        if 'Relation Name' in node:
            rel_name = node['Relation Name']
            if rel_name is None:
                # Узлы без имени (Aggregate, Lateral Subquery Scan и т.д.) — пропускаем
                pass
            else:
                schema = node.get('Schema', '')
                full_name = f"{schema}.{rel_name}" if schema else rel_name

                print(f"    🔍 Обработка узла: {full_name}")

                # Проверяем, является ли объект представлением с известным маппингом
                if view_to_tables_map and full_name in view_to_tables_map:
                    physical_tables = view_to_tables_map[full_name]
                    print(f"    📋 Представление {full_name} -> физические таблицы: {physical_tables}")

                    # Для представления используем размеры первой физической таблицы
                    found = False
                    for table_key, rows in user_table_sizes.items():
                        for phys_table in physical_tables:
                            if phys_table in table_key or table_key in phys_table:
                                node['Plan Rows'] = rows
                                if 'Plan Width' not in node or node['Plan Width'] == 0:
                                    node['Plan Width'] = 100
                                print(f"    ✅ {rel_name} (представление) -> {rows:,} строк (через {phys_table})")
                                found = True
                                break
                        if found:
                            break
                    if not found:
                        print(f"    ❌ {rel_name} (представление) - физические таблицы не найдены в пользовательских размерах")

                # Если это не представление или маппинг не дал результата, ищем прямое совпадение
                else:
                    # Формируем возможные имена для поиска
                    possible_names = [
                        rel_name,
                        rel_name.lower(),
                        full_name,
                        full_name.lower(),
                    ]

                    # Добавляем имя без схемы, если есть схема
                    if schema:
                        possible_names.append(rel_name)
                        possible_names.append(rel_name.lower())

                    # Убираем дубликаты
                    possible_names = list(set(possible_names))
                    print(f"    Возможные имена для поиска: {possible_names}")

                    # Ищем совпадение
                    found = False
                    for table_key, rows in user_table_sizes.items():
                        table_key_lower = table_key.lower()
                        for name in possible_names:
                            if name and (name.lower() in table_key_lower or table_key_lower in name.lower()):
                                node['Plan Rows'] = rows
                                if 'Plan Width' not in node or node['Plan Width'] == 0:
                                    node['Plan Width'] = 100
                                print(f"    ✅ {rel_name} -> {rows:,} строк (matched with {table_key})")
                                found = True
                                break
                        if found:
                            break

                    if not found:
                        print(f"    ❌ {rel_name} не найдено в пользовательских размерах")
        
        # Рекурсивно обрабатываем дочерние узлы
        if 'Plans' in node:
            for child in node['Plans']:
                adjust_node(child)
    
    # Начинаем обработку с корневого узла
    if 'Plan' in plan_copy:
        adjust_node(plan_copy['Plan'])
    else:
        adjust_node(plan_copy)
    
    return plan_copy


def compute_block_load(plan: dict, multipliers: Dict[str, float] = None, segments: int = 120) -> Dict[str, Any]:
    """
    Вычисляет нагрузку блока на основе скорректированного плана.
    """
    if multipliers is None:
        multipliers = DEFAULT_MULTIPLIERS
    
    print(f"    📊 Вычисление нагрузки блока (segments={segments})")
    
    def extract_max_memory(node: dict, depth: int = 0) -> float:
        indent = "      " * depth
        node_type = node.get('Node Type', 'Unknown')
        rows = node.get('Plan Rows', 0)
        width = node.get('Plan Width', 100)
        mult = multipliers.get(node_type, 1.0)
        
        # Детальный вывод для каждого узла
        print(f"{indent}📌 Узел: {node_type}")
        print(f"{indent}   Строки: {rows:,}")
        print(f"{indent}   Ширина: {width} байт")
        print(f"{indent}   Множитель: {mult}")
        
        # Объём данных в этом узле (GB) на сегмент
        node_gb = (rows * width * mult) / 1e9 / segments
        print(f"{indent}   Нагрузка узла: {node_gb:.6f} GB")
        
        max_child = 0.0
        if 'Plans' in node:
            for child in node['Plans']:
                child_gb = extract_max_memory(child, depth + 1)
                max_child = max(max_child, child_gb)
        
        result = max(node_gb, max_child)
        print(f"{indent}🔝 Максимум для узла {node_type}: {result:.6f} GB")
        return result
    
    # Начинаем с корневого узла
    if 'Plan' in plan:
        max_memory_gb = extract_max_memory(plan['Plan'])
    else:
        max_memory_gb = extract_max_memory(plan)
    
    total_rows = plan.get('Plan Rows', 0)
    
    print(f"    📊 Итоговая нагрузка блока: {max_memory_gb:.6f} GB")
    print(f"    📊 Всего строк в плане: {total_rows:,}")
    
    return {
        'max_memory_gb': round(max_memory_gb, 3),
        'total_rows': total_rows,
    }


def diagnose_heavy_block(
    sql: str,
    tables_in_block: List[tuple],
    user_table_sizes: Dict[str, int],
    discovered_tables: Dict[str, Any],
) -> Dict[str, str]:
    """
    Определяет причину тяжести и даёт рекомендацию для блока, вызвавшего зависание/таймаут.
    """
    reasons = []
    recommendations = []
    sql_upper = (sql or '').upper()

    # Собираем размеры таблиц
    table_rows: List[tuple] = []
    for sch, tbl in tables_in_block:
        full_name = f"{sch}.{tbl}" if sch else tbl
        full_lower = full_name.lower()
        rows = None
        for key, val in (user_table_sizes or {}).items():
            if key.lower() in full_lower or full_lower in key.lower():
                rows = val
                break
        if rows is None and discovered_tables:
            for key, info in discovered_tables.items():
                if key.lower() in full_lower or full_lower in key.lower():
                    rows = info.get('current_rows', 0)
                    break
        if rows is not None and rows > 0:
            table_rows.append((full_name, rows))

    # Причина: очень большие таблицы
    heavy_tables = [(n, r) for n, r in table_rows if r >= 1_000_000_000]
    if heavy_tables:
        names = [f"{n} (~{r:,} строк)" for n, r in heavy_tables[:3]]
        reasons.append(f"Обращение к крупным таблицам: {', '.join(names)}")
        recommendations.append(
            "Добавьте фильтры (WHERE) по партиционирующим колонкам или датам. "
            "Рассмотрите партиционирование таблиц."
        )

    # Причина: много таблиц в JOIN
    if len(tables_in_block) >= 5:
        reasons.append(f"Сложный запрос: {len(tables_in_block)} таблиц в JOIN")
        recommendations.append(
            "Разбейте на подзапросы с CTE или временными таблицами. "
            "Упростите план выполнения."
        )

    # Причина: агрегация по большой таблице
    if table_rows and any(r in sql_upper for r in ('MIN(', 'MAX(', 'SUM(', 'COUNT(', 'AVG(', 'GROUP BY')):
        max_rows = max(r for _, r in table_rows)
        if max_rows >= 100_000_000:
            reasons.append("Агрегация (MIN/MAX/SUM/GROUP BY) по таблице с сотнями миллионов строк")
            recommendations.append(
                "Используйте предварительную агрегацию в материализованных представлениях "
                "или инкрементальный расчёт."
            )

    # Причина: полное сканирование без фильтров
    if 'WHERE' not in sql_upper and 'JOIN' not in sql_upper and table_rows:
        max_rows = max(r for _, r in table_rows)
        if max_rows >= 10_000_000:
            reasons.append("Полное сканирование таблицы без фильтров WHERE")
            recommendations.append("Добавьте условия WHERE для ограничения объёма данных.")

    # Причина: INSERT/SELECT
    if 'INSERT' in sql_upper and 'SELECT' in sql_upper:
        if table_rows and max(r for _, r in table_rows) >= 100_000_000:
            reasons.append("Массовая вставка из крупной таблицы")
            recommendations.append(
                "Используйте batch-вставку (LIMIT + цикл) или UNLOAD/COPY для больших объёмов."
            )

    reason = "; ".join(reasons) if reasons else "Синтез плана не завершён (таймаут GigaChat). Запрос, вероятно, сложный."
    rec = " ".join(recommendations) if recommendations else (
        "Проверьте запрос на предмет полных сканов и тяжёлых JOIN. "
        "Рассмотрите выполнение с подключением к БД для точного EXPLAIN."
    )
    return {"reason": reason, "recommendation": rec}


def estimate_block_load_from_tables(
    tables_in_block: List[tuple],
    user_table_sizes: Dict[str, int],
    discovered_tables: Dict[str, Any],
    segments: int = 120,
    mult_unknown: float = 2.0,
    sql: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Оценка нагрузки блока по размерам таблиц, когда план недоступен (таймаут GigaChat, ошибка и т.д.).
    Вывод: запрос, вызвавший зависание, скорее всего тяжёлый — используем консервативную оценку.
    """
    total_rows = 0
    max_gb_per_table = 0.0

    for sch, tbl in tables_in_block:
        full_name = f"{sch}.{tbl}" if sch else tbl
        full_lower = full_name.lower()

        rows = None
        for key, val in (user_table_sizes or {}).items():
            if key.lower() in full_lower or full_lower in key.lower():
                rows = val
                break
        if rows is None and discovered_tables:
            for key, info in discovered_tables.items():
                if key.lower() in full_lower or full_lower in key.lower():
                    rows = info.get('current_rows', 0)
                    break

        if rows is None or rows <= 0:
            continue

        width = 100
        if discovered_tables:
            for key, info in discovered_tables.items():
                if key.lower() in full_lower or full_lower in key.lower():
                    width = info.get('avg_row_size_bytes', 100) or 100
                    break

        gb = (rows * width * mult_unknown) / 1e9 / segments
        max_gb_per_table = max(max_gb_per_table, gb)
        total_rows += rows

    max_memory_gb = round(max_gb_per_table, 3)
    out = {
        'max_memory_gb': max_memory_gb,
        'total_rows': total_rows,
        'fallback_estimate': True,
    }
    if sql:
        diag = diagnose_heavy_block(sql, tables_in_block, user_table_sizes, discovered_tables)
        out['heavy_reason'] = diag['reason']
        out['heavy_recommendation'] = diag['recommendation']
    return out


def estimate_execution_time(plan: dict, row_coeff: float = 1.0, cost_per_second: float = 100000.0) -> float:
    """
    Оценивает время выполнения на основе стоимости (Total Cost).
    Предполагаем, что 1 cost unit ≈ 1/100000 секунды (настраивается).
    """
    total_cost = plan.get('Total Cost', 0)
    adjusted_cost = total_cost * row_coeff
    return adjusted_cost / cost_per_second


def get_top_blocks(block_results: List[Dict], top_n: int = 3) -> List[Dict]:
    """
    Возвращает топ-N блоков по максимальной нагрузке.
    """
    sorted_blocks = sorted(block_results, key=lambda x: x['load']['max_memory_gb'], reverse=True)
    return sorted_blocks[:top_n]


def calculate_total_load(block_results: List[Dict], segments: int = 120, ram_per_seg_gb: float = 153.6) -> Dict:
    """
    Суммирует нагрузку по всем блокам и определяет риск.
    """
    total_memory_gb = sum(b['load']['max_memory_gb'] for b in block_results)
    max_utilization = total_memory_gb / ram_per_seg_gb * 100 if ram_per_seg_gb > 0 else 0
    
    if max_utilization > 40:
        risk = "ВЫСОКИЙ"
    elif max_utilization > 15:
        risk = "СРЕДНИЙ"
    else:
        risk = "НИЗКИЙ"
    
    total_time_sec = sum(b.get('estimated_time', 0) for b in block_results)
    
    return {
        'total_memory_gb': round(total_memory_gb, 2),
        'max_utilization': round(max_utilization, 2),
        'risk': risk,
        'estimated_time_sec': round(total_time_sec, 2),
    }