from typing import Dict, List, Any

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

def compute_block_load(plan: dict, multipliers: Dict[str, float] = None, segments: int = 120) -> Dict[str, Any]:
    """
    Оценивает пиковую нагрузку на сегмент для одного блока.
    Возвращает словарь с максимальной памятью (GB), общим количеством строк и т.д.
    """
    if multipliers is None:
        multipliers = DEFAULT_MULTIPLIERS
    
    def extract_max_memory(node: dict) -> float:
        node_type = node.get('Node Type')
        rows = node.get('Plan Rows', 0)
        width = node.get('Plan Width', 0)
        mult = multipliers.get(node_type, 1.0)
        # Объём данных в этом узле (GB) на сегмент (приблизительно)
        node_gb = (rows * width * mult) / 1e9 / segments
        max_child = 0.0
        if 'Plans' in node:
            for child in node['Plans']:
                max_child = max(max_child, extract_max_memory(child))
        return max(node_gb, max_child)
    
    max_memory_gb = extract_max_memory(plan)
    total_rows = plan.get('Plan Rows', 0)
    
    return {
        'max_memory_gb': max_memory_gb,
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
    Возвращает словарь с общей памятью, риском и оценочным временем.
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