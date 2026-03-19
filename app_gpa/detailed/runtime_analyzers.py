from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, Sequence

if TYPE_CHECKING:
    from .detailed_analyzer import ClusterConfig, DetailedGreenplumFunctionAnalyzer


class RuntimeAnalyzer(Protocol):
    stack: str
    blocks: List[str]
    block_types: List[str]
    input_type: Optional[str]
    discovered_tables: Dict[str, Dict[str, Any]]
    view_to_tables_map: Dict[str, Any]
    variables: Dict[str, Any]
    function_params: List[str]
    func_name: str
    temp_tables: set
    physical_tables: set

    def reset_for_rerun(self) -> None:
        ...

    def discover_tables(self, source_text: str) -> Dict[str, Any]:
        ...

    def analyze_with_user_sizes(
        self,
        params: Sequence[str],
        user_sizes: Dict[str, int],
        *,
        analysis_mode: str,
        plan_source: str,
        agent_credentials: Optional[str] = None,
        agent_scope: Optional[str] = None,
        agent_chat_model: Optional[str] = None,
        agent_embedding_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        ...


def _normalize_object_name(name: str) -> str:
    value = str(name or "").strip().strip('"').strip("'")
    if not value:
        return ""
    return value


def _split_schema_table(value: str) -> tuple[str, str]:
    clean = _normalize_object_name(value)
    if "." in clean:
        schema, table = clean.split(".", 1)
        return schema.strip() or "default", table.strip()
    return "default", clean


def _build_table_info(name: str, avg_row_size_bytes: float) -> Dict[str, Any]:
    schema, table = _split_schema_table(name)
    return {
        "schema": schema,
        "table": table,
        "current_rows": 0,
        "size_gb": 0.0,
        "avg_row_size_bytes": avg_row_size_bytes,
        "columns": 0,
        "user_rows": 0,
    }


def _parse_memory_to_gb(value: Any, default: float = 0.0) -> float:
    text = str(value or "").strip().lower()
    if not text:
        return default
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([kmgt]?)b?$", text)
    if not match:
        return default
    number = float(match.group(1))
    unit = match.group(2)
    if unit == "k":
        return number / (1024 ** 2)
    if unit == "m":
        return number / 1024
    if unit == "g":
        return number
    if unit == "t":
        return number * 1024
    return number / (1024 ** 3)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_json_document(value: Any) -> Any:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_named_mapping(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    if all(isinstance(v, dict) for v in payload.values()):
        return {_normalize_object_name(k): dict(v) for k, v in payload.items() if _normalize_object_name(k)}
    return {}


def _extract_named_list(payload: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(payload, list):
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = _normalize_object_name(item.get("name") or item.get("table") or item.get("source") or item.get("dataset"))
        if name:
            result[name] = dict(item)
    return result


def _extract_profile_aliases(profile: Dict[str, Any]) -> Dict[str, float]:
    aliases: Dict[str, float] = {}
    alias_peak = profile.get("peakMemoryGb") or profile.get("peak_memory")
    alias_shuffle_read = profile.get("shuffleReadGb") or profile.get("shuffle_read")
    alias_shuffle_write = profile.get("shuffleWriteGb") or profile.get("shuffle_write")
    if alias_peak is not None:
        aliases["peak_memory_gb"] = _safe_float(alias_peak, 0.0)
    if alias_shuffle_read is not None:
        aliases["shuffle_read_gb"] = _safe_float(alias_shuffle_read, 0.0)
    if alias_shuffle_write is not None:
        aliases["shuffle_write_gb"] = _safe_float(alias_shuffle_write, 0.0)
    return aliases


def _apply_stage_aggregates(profile: Dict[str, Any]) -> Dict[str, Any]:
    stages = profile.get("stages")
    if not isinstance(stages, list):
        return profile
    if "peak_memory_gb" not in profile:
        profile["peak_memory_gb"] = max(
            (_safe_float(item.get("peak_memory_gb"), 0.0) for item in stages if isinstance(item, dict)),
            default=0.0,
        )
    if "shuffle_read_gb" not in profile:
        profile["shuffle_read_gb"] = sum(_safe_float(item.get("shuffle_read_gb"), 0.0) for item in stages if isinstance(item, dict))
    if "shuffle_write_gb" not in profile:
        profile["shuffle_write_gb"] = sum(_safe_float(item.get("shuffle_write_gb"), 0.0) for item in stages if isinstance(item, dict))
    return profile


def _normalize_metadata_payload(payload: Any) -> Dict[str, Dict[str, Any]]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        nested_metadata = payload.get("metadata") or payload.get("snapshot")
        if isinstance(nested_metadata, (dict, list)):
            payload = nested_metadata
        list_payload = next(
            (payload.get(key) for key in ("tables", "sources", "datasets", "objects", "entities") if isinstance(payload.get(key), list)),
            None,
        )
        if list_payload is not None:
            payload = list_payload
        else:
            return _extract_named_mapping(payload)
    if isinstance(payload, list):
        return _extract_named_list(payload)
    return {}


def _normalize_profile_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    nested_profile = payload.get("runtime_profile") or payload.get("profile") or payload.get("telemetry") or payload.get("metrics")
    if isinstance(nested_profile, dict):
        payload = nested_profile
    profile = dict(payload)
    for key, value in _extract_profile_aliases(profile).items():
        profile.setdefault(key, value)
    return _apply_stage_aggregates(profile)


def _derive_analysis_quality(metadata_payload: Dict[str, Dict[str, Any]], profile_payload: Dict[str, Any], has_runtime: bool) -> str:
    if profile_payload:
        return "profile_enriched"
    if metadata_payload:
        return "metadata_enriched"
    if has_runtime:
        return "runtime_hinted"
    return "approximate"


def _estimate_risk(total_memory_gb: float) -> str:
    if total_memory_gb >= 16:
        return "ВЫСОКИЙ"
    if total_memory_gb >= 4:
        return "СРЕДНИЙ"
    return "НИЗКИЙ"


def _unique(values: Sequence[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        clean = _normalize_object_name(value)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out


class BaseMvpRuntimeAnalyzer:
    stack = "runtime"
    source_type = "code"
    avg_row_size_bytes = 256.0

    def __init__(self, runtime_config: Optional[Dict[str, Any]] = None) -> None:
        self.runtime_config = dict(runtime_config or {})
        self.metadata_payload = _normalize_metadata_payload(_parse_json_document(self.runtime_config.get("metadata_json")))
        self.profile_payload = _normalize_profile_payload(_parse_json_document(self.runtime_config.get("profile_json")))
        self.blocks: List[str] = []
        self.block_types: List[str] = []
        self.input_type: Optional[str] = None
        self.discovered_tables: Dict[str, Dict[str, Any]] = {}
        self.view_to_tables_map: Dict[str, Any] = {}
        self.variables: Dict[str, Any] = {}
        self.function_params: List[str] = []
        self.func_name = f"{self.stack}_job"
        self.temp_tables: set = set()
        self.physical_tables: set = set()
        self.runtime_summary = self._build_runtime_summary()

    def reset_for_rerun(self) -> None:
        self.variables = {}

    def _build_runtime_summary(self) -> Dict[str, Any]:
        quality = _derive_analysis_quality(self.metadata_payload, self.profile_payload, bool(self.runtime_config.get("master_url")))
        return {
            "runtime_label": self.stack.upper(),
            "master_url": str(self.runtime_config.get("master_url") or "").strip() or None,
            "quality": quality,
            "default_schema": "default",
            "capacity_gb": 0.0,
            "notes": ["Оценка построена без нативного коннектора и использует runtime hints из формы."],
            "metadata_sources": len(self.metadata_payload),
            "profile_attached": bool(self.profile_payload),
        }

    def _extract_blocks(self, source_text: str) -> List[str]:
        text = str(source_text or "").strip()
        return [text] if text else []

    def _extract_objects(self, _source_text: str) -> List[str]:
        return []

    def _detect_antipatterns(self, _block_sql: str) -> List[Dict[str, str]]:
        return []

    def _block_type(self, _block_sql: str) -> str:
        return "OTHER"

    def _category(self) -> str:
        return self.stack.upper()

    def _decorate_table_info(self, name: str, info: Dict[str, Any]) -> Dict[str, Any]:
        metadata = self._metadata_entry(name)
        if metadata:
            info["current_rows"] = int(metadata.get("rows") or metadata.get("row_count") or metadata.get("current_rows") or info["current_rows"])
            info["size_gb"] = _safe_float(metadata.get("size_gb") or metadata.get("table_size_gb") or metadata.get("size"), info["size_gb"])
            info["avg_row_size_bytes"] = _safe_float(metadata.get("avg_row_size_bytes") or metadata.get("row_size_bytes"), info["avg_row_size_bytes"])
            info["columns"] = int(metadata.get("columns") or metadata.get("column_count") or info["columns"])
            info["ingested_metadata"] = True
        return info

    def _complexity_multiplier(self, block_sql: str) -> float:
        del block_sql
        return 1.0

    def _analysis_quality(self) -> str:
        return str(self.runtime_summary.get("quality") or "approximate")

    def _metadata_entry(self, name: str) -> Dict[str, Any]:
        if name in self.metadata_payload:
            return self.metadata_payload[name]
        schema, table = _split_schema_table(name)
        composed = f"{schema}.{table}"
        if composed in self.metadata_payload:
            return self.metadata_payload[composed]
        return {}

    def _profile_multiplier(self) -> float:
        if not self.profile_payload:
            return 1.0
        peak_memory_gb = _safe_float(self.profile_payload.get("peak_memory_gb"), 0.0)
        shuffle_read_gb = _safe_float(self.profile_payload.get("shuffle_read_gb"), 0.0)
        shuffle_write_gb = _safe_float(self.profile_payload.get("shuffle_write_gb"), 0.0)
        multiplier = 1.0
        multiplier += min(0.6, peak_memory_gb / 128.0)
        multiplier += min(0.35, (shuffle_read_gb + shuffle_write_gb) / 512.0)
        return multiplier

    def discover_tables(self, source_text: str) -> Dict[str, Any]:
        text = str(source_text or "")
        self.input_type = self.source_type
        self.blocks = self._extract_blocks(text)
        self.block_types = [self._block_type(block) for block in self.blocks]
        objects = _unique(list(self._extract_objects(text)) + list(self.metadata_payload.keys()))
        self.discovered_tables = {
            name: self._decorate_table_info(name, _build_table_info(name, self.avg_row_size_bytes))
            for name in objects
        }
        self.physical_tables = {_split_schema_table(name) for name in objects}
        return {
            "input_type": self.input_type,
            "function": self.func_name,
            "blocks_count": len(self.blocks),
            "block_types": self.block_types,
            "temp_tables": list(self.temp_tables),
            "discovered_tables": self.discovered_tables,
            "view_to_tables_map": self.view_to_tables_map,
            "physical_tables_count": len(self.discovered_tables),
            "objects_referenced_in_blocks": len(self.discovered_tables),
            "variables": self.variables,
            "function_params": self.function_params,
            "status": "tables_discovered",
            "agent_requested_ddl": [],
            "use_agent_path": False,
            "stack": self.stack,
            "runtime_context": self.runtime_summary,
            "analysis_quality": self._analysis_quality(),
        }

    def analyze_with_user_sizes(
        self,
        params: Sequence[str],
        user_sizes: Dict[str, int],
        *,
        analysis_mode: str,
        plan_source: str,
        agent_credentials: Optional[str] = None,
        agent_scope: Optional[str] = None,
        agent_chat_model: Optional[str] = None,
        agent_embedding_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        del agent_credentials, agent_scope, agent_chat_model, agent_embedding_model
        block_details: List[Dict[str, Any]] = []
        total_memory_gb = 0.0
        problematic_blocks: List[Dict[str, Any]] = []
        recommendations: List[str] = []
        cluster_capacity_gb = float(self.runtime_summary.get("capacity_gb") or 0.0)

        for index, block_sql in enumerate(self.blocks, start=1):
            objects = _unique(self._extract_objects(block_sql))
            total_rows = 0
            for name in objects:
                info = self.discovered_tables.get(name) or {}
                base_rows = int(info.get("current_rows") or 0)
                total_rows += int(user_sizes.get(name, base_rows))
            complexity_multiplier = self._complexity_multiplier(block_sql)
            complexity_multiplier *= self._profile_multiplier()
            estimated_memory = max(
                0.01,
                ((total_rows or 100000) * self.avg_row_size_bytes) / float(1024 ** 3) * complexity_multiplier,
            )
            anti_patterns = self._detect_antipatterns(block_sql)
            block_result = {
                "index": index,
                "type": self._block_type(block_sql),
                "category": self._category(),
                "max_memory_gb": round(estimated_memory, 3),
                "total_rows": total_rows,
                "tables": objects,
                "sql_preview": block_sql[:180],
                "sql_full": block_sql,
                "anti_patterns": anti_patterns,
                "fallback_estimate": True,
                "heavy_reason": "Использована MVP-оценка по объёму данных выбранного стека.",
                "heavy_recommendation": "Уточните runtime-конфигурацию и объёмы данных для более точного расчёта.",
                "complexity_multiplier": round(complexity_multiplier, 2),
            }
            block_details.append(block_result)
            total_memory_gb += estimated_memory
            if anti_patterns:
                problematic_blocks.append(block_result | {"block_hedge": [item.get("hedge", "") for item in anti_patterns if item.get("hedge")]})
                recommendations.extend([item.get("hedge", "") for item in anti_patterns if item.get("hedge")])

        top_blocks = sorted(block_details, key=lambda item: item.get("max_memory_gb", 0), reverse=True)[:3]
        memory_pressure = round(total_memory_gb / cluster_capacity_gb, 3) if cluster_capacity_gb > 0 else None
        risk_input = total_memory_gb if memory_pressure is None else max(total_memory_gb, memory_pressure * 8)
        result = {
            "function": self.func_name,
            "stack": self.stack,
            "analysis_mode": analysis_mode,
            "plan_source": plan_source,
            "blocks_count": len(self.blocks),
            "analyzed_blocks": len(block_details),
            "block_details": block_details,
            "top_blocks": top_blocks,
            "discovered_tables": self.discovered_tables,
            "user_table_sizes": user_sizes,
            "user_params": list(params),
            "total_memory_gb": round(total_memory_gb, 3),
            "antipattern_added_gb": round(sum(0.15 for block in problematic_blocks if block.get("anti_patterns")), 3),
            "estimated_time_sec": round(max(3.0, total_memory_gb * 12 + len(block_details) * 1.5), 1),
            "risk": _estimate_risk(risk_input),
            "problematic_blocks": problematic_blocks,
            "general_hedge_recommendations": _unique([item for item in recommendations if item]),
            "agent_errors": [],
            "runtime_context": self.runtime_summary,
            "analysis_quality": self._analysis_quality(),
            "cluster_capacity_gb": round(cluster_capacity_gb, 3),
            "memory_pressure": memory_pressure,
        }
        return result


class SparkRuntimeAnalyzer(BaseMvpRuntimeAnalyzer):
    stack = "spark"
    source_type = "spark_sql"
    avg_row_size_bytes = 256.0

    def _build_runtime_summary(self) -> Dict[str, Any]:
        executors = max(1, _safe_int(self.runtime_config.get("executor_instances"), 4))
        cores = max(1, _safe_int(self.runtime_config.get("executor_cores"), 4))
        executor_memory_gb = max(1.0, _parse_memory_to_gb(self.runtime_config.get("executor_memory"), 8.0))
        capacity_gb = executors * executor_memory_gb * 0.72
        namespace = str(self.runtime_config.get("namespace") or "").strip() or "default"
        catalog = str(self.runtime_config.get("catalog") or "").strip() or "hive_metastore"
        return {
            "runtime_label": "Spark",
            "master_url": str(self.runtime_config.get("master_url") or "").strip() or None,
            "catalog": catalog,
            "namespace": namespace,
            "quality": _derive_analysis_quality(self.metadata_payload, self.profile_payload, bool(self.runtime_config.get("master_url"))),
            "default_schema": namespace,
            "capacity_gb": round(capacity_gb, 3),
            "executors": executors,
            "executor_cores": cores,
            "executor_memory_gb": round(executor_memory_gb, 3),
            "notes": [
                "Оценка использует Spark runtime hints: executors, cores и executor memory.",
                "Без нативного Spark connector размеры таблиц и планы остаются approximate.",
            ],
            "metadata_sources": len(self.metadata_payload),
            "profile_attached": bool(self.profile_payload),
        }

    def _extract_blocks(self, source_text: str) -> List[str]:
        text = str(source_text or "")
        parts = [part.strip() for part in re.split(r";\s*(?:\n|$)", text) if part.strip()]
        return parts or ([text.strip()] if text.strip() else [])

    def _extract_objects(self, source_text: str) -> List[str]:
        matches = re.findall(
            r"\b(?:from|join|into|table|cache\s+table)\s+([A-Z_][A-Z0-9$]*(?:\.[A-Z_][A-Z0-9$]*)?)",
            str(source_text or ""),
            flags=re.IGNORECASE,
        )
        return [name for name in matches if name.lower() not in {"select", "where", "group", "order"}]

    def _detect_antipatterns(self, block_sql: str) -> List[Dict[str, str]]:
        issues: List[Dict[str, str]] = []
        if re.search(r"\bselect\s+\*\b", block_sql, flags=re.IGNORECASE):
            issues.append({"pattern": "SELECT *", "reason": "Широкая выборка может увеличивать shuffle и объём чтения.", "hedge": "Ограничьте список колонок."})
        if re.search(r"\bexplode\s*\(", block_sql, flags=re.IGNORECASE) and not re.search(r"\blateral\s+view\b", block_sql, flags=re.IGNORECASE):
            issues.append({"pattern": "explode()", "reason": "Разворот массивов часто увеличивает количество строк.", "hedge": "Проверьте cardinality и необходимость `LATERAL VIEW`."})
        if re.search(r"\binsert\s+overwrite\b", block_sql, flags=re.IGNORECASE):
            issues.append({"pattern": "INSERT OVERWRITE", "reason": "Операция может затронуть большой объём данных.", "hedge": "Проверьте партиции и область перезаписи."})
        return issues

    def _decorate_table_info(self, name: str, info: Dict[str, Any]) -> Dict[str, Any]:
        info = super()._decorate_table_info(name, info)
        if "." not in name:
            info["schema"] = str(self.runtime_summary.get("default_schema") or "default")
        info["catalog"] = self.runtime_summary.get("catalog")
        info["source_kind"] = "spark_table"
        if info.get("ingested_metadata"):
            info["source_kind"] = "spark_table_snapshot"
        return info

    def _block_type(self, block_sql: str) -> str:
        match = re.match(r"\s*([A-Za-z]+)", block_sql or "")
        return (match.group(1) if match else "SQL").upper()

    def _category(self) -> str:
        return "Spark SQL"

    def _complexity_multiplier(self, block_sql: str) -> float:
        sql = block_sql.lower()
        multiplier = 1.15
        multiplier += sql.count(" join ") * 0.28
        multiplier += sql.count(" union ") * 0.18
        multiplier += sql.count(" over(") * 0.3
        if "group by" in sql:
            multiplier += 0.24
        if "order by" in sql or "sort by" in sql:
            multiplier += 0.18
        if "explode(" in sql:
            multiplier += 0.4
        if "insert overwrite" in sql:
            multiplier += 0.25
        return multiplier


class PySparkRuntimeAnalyzer(BaseMvpRuntimeAnalyzer):
    stack = "pyspark"
    source_type = "pyspark"
    avg_row_size_bytes = 192.0

    def _build_runtime_summary(self) -> Dict[str, Any]:
        executors = max(1, _safe_int(self.runtime_config.get("executor_instances"), 4))
        executor_memory_gb = max(1.0, _parse_memory_to_gb(self.runtime_config.get("executor_memory"), 8.0))
        capacity_gb = executors * executor_memory_gb * 0.68
        session_name = str(self.runtime_config.get("session_name") or "").strip() or "gpa-pyspark"
        return {
            "runtime_label": "PySpark",
            "master_url": str(self.runtime_config.get("master_url") or "").strip() or None,
            "session_name": session_name,
            "quality": _derive_analysis_quality(self.metadata_payload, self.profile_payload, bool(self.runtime_config.get("master_url"))),
            "default_schema": "default",
            "capacity_gb": round(capacity_gb, 3),
            "executors": executors,
            "executor_memory_gb": round(executor_memory_gb, 3),
            "notes": [
                "Оценка использует PySpark session hints: master URL, session name и executor memory.",
                "Без нативного PySpark runtime profile оценка остается approximate.",
            ],
            "metadata_sources": len(self.metadata_payload),
            "profile_attached": bool(self.profile_payload),
        }

    def _extract_blocks(self, source_text: str) -> List[str]:
        text = str(source_text or "").strip()
        sql_blocks = re.findall(r"spark\.sql\(\s*(?:'''|\"\"\"|'|\")(.*?)(?:'''|\"\"\"|'|\")\s*\)", text, flags=re.IGNORECASE | re.DOTALL)
        if sql_blocks:
            blocks = [block.strip() for block in sql_blocks if block.strip()]
            if blocks:
                return blocks
        sections = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        return sections or ([text] if text else [])

    def _extract_objects(self, source_text: str) -> List[str]:
        text = str(source_text or "")
        objects = re.findall(r"spark(?:\.read)?\.table\(\s*[\"']([^\"']+)[\"']\s*\)", text)
        objects.extend(re.findall(r"(?:saveAsTable|insertInto)\(\s*[\"']([^\"']+)[\"']\s*\)", text))
        for sql_text in re.findall(r"spark\.sql\(\s*(?:'''|\"\"\"|'|\")(.*?)(?:'''|\"\"\"|'|\")\s*\)", text, flags=re.IGNORECASE | re.DOTALL):
            objects.extend(re.findall(
                r"\b(?:from|join|into|table)\s+([A-Z_][A-Z0-9$]*(?:\.[A-Z_][A-Z0-9$]*)?)",
                sql_text,
                flags=re.IGNORECASE,
            ))
        return objects

    def _detect_antipatterns(self, block_sql: str) -> List[Dict[str, str]]:
        issues: List[Dict[str, str]] = []
        if re.search(r"\.collect\s*\(", block_sql):
            issues.append({"pattern": "collect()", "reason": "Полная выгрузка данных на драйвер может стать узким местом.", "hedge": "Ограничьте выборку или используйте агрегирование на кластере."})
        if re.search(r"\.toPandas\s*\(", block_sql):
            issues.append({"pattern": "toPandas()", "reason": "Материализация в pandas может привести к OOM на драйвере.", "hedge": "Перед toPandas() ограничьте объём данных."})
        if re.search(r"\budf\s*\(", block_sql) and not re.search(r"\bpandas_udf\s*\(", block_sql):
            issues.append({"pattern": "udf()", "reason": "Обычные Python UDF часто хуже оптимизируются.", "hedge": "Проверьте built-in функции или pandas_udf."})
        return issues

    def _decorate_table_info(self, name: str, info: Dict[str, Any]) -> Dict[str, Any]:
        info = super()._decorate_table_info(name, info)
        info["source_kind"] = "pyspark_dataset"
        info["session_name"] = self.runtime_summary.get("session_name")
        if info.get("ingested_metadata"):
            info["source_kind"] = "pyspark_dataset_snapshot"
        return info

    def _block_type(self, block_sql: str) -> str:
        if "spark.sql" in block_sql.lower():
            return "SPARK.SQL"
        if ".join(" in block_sql or ".groupBy(" in block_sql or ".select(" in block_sql:
            return "DATAFRAME"
        return "PYSPARK"

    def _category(self) -> str:
        return "PySpark"

    def _complexity_multiplier(self, block_sql: str) -> float:
        code = block_sql.lower()
        multiplier = 1.1
        multiplier += code.count(".join(") * 0.24
        multiplier += code.count(".groupby(") * 0.18
        multiplier += code.count(".withcolumn(") * 0.08
        multiplier += code.count("spark.sql(") * 0.16
        if ".collect(" in code:
            multiplier += 0.45
        if ".topandas(" in code:
            multiplier += 0.55
        if "udf(" in code and "pandas_udf(" not in code:
            multiplier += 0.35
        return multiplier


def create_runtime_analyzer(
    stack: str,
    cluster_config: Optional["ClusterConfig"] = None,
    runtime_config: Optional[Dict[str, Any]] = None,
) -> RuntimeAnalyzer:
    if stack == "spark":
        return SparkRuntimeAnalyzer(runtime_config=runtime_config)
    if stack == "pyspark":
        return PySparkRuntimeAnalyzer(runtime_config=runtime_config)
    from .detailed_analyzer import ClusterConfig, DetailedGreenplumFunctionAnalyzer

    return DetailedGreenplumFunctionAnalyzer(config=cluster_config or ClusterConfig())
