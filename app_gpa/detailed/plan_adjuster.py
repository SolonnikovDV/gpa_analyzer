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
    
    # Выводим маппинг представлений
    if view_to_tables_map:
        print(f"    Маппинг представлений: {view_to_tables_map}")
    else:
        print(f"    ⚠️ Маппинг представлений отсутствует!")
    
    def adjust_node(node: dict):
        if 'Relation Name' in node:
            rel_name = node['Relation Name']
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