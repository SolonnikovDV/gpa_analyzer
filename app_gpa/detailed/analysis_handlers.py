from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .detailed_analyzer import ClusterConfig
from .runtime_analyzers import create_runtime_analyzer
from .runtime_registry import get_runtime_descriptor, normalize_stack


@dataclass
class DiscoveryRuntimeContext:
    analysis_mode: str
    plan_source: str
    use_db: bool
    stack: str
    runtime_descriptor: Any
    cluster_config: ClusterConfig
    runtime_analysis_config: Dict[str, Any]
    analyzer: Any


@dataclass
class AnalysisRuntimeContext:
    analysis_mode: str
    plan_source: str
    use_db: bool
    stack: str
    runtime_descriptor: Any
    analyzer: Any
    agent_credentials: Any
    agent_scope: Any


def _mode_label(analysis_mode: str, use_db: bool) -> str:
    is_pure_agent = analysis_mode == "hybrid" and not use_db
    if is_pure_agent:
        return "чистый агент"
    if analysis_mode == "hybrid":
        return "гибрид"
    return "логика"


def _plan_label(plan_source: str) -> str:
    return "агент (синтез)" if plan_source == "agent" else "БД (EXPLAIN)"


def log_runtime_execution_banner(
    *,
    stack_label: str,
    analysis_mode: str,
    plan_source: str,
    use_db: bool,
    phase: str,
    agent_chat_model: Optional[str] = None,
    agent_embedding_model: Optional[str] = None,
) -> None:
    mode_label = _mode_label(analysis_mode, use_db)
    plan_label = _plan_label(plan_source)
    print("=" * 60)
    print(f"Стек: {stack_label}")
    print(f"Режим анализа: {mode_label}")
    print(f"Источник плана запроса: {plan_label}")
    if agent_chat_model or agent_embedding_model:
        print(
            f"Модели GigaChat (выбранные для сессии): чат={agent_chat_model or 'цепочка по умолчанию'}, "
            f"эмбеддинги={agent_embedding_model or 'цепочка по умолчанию'}"
        )
    if phase == "discovery":
        if analysis_mode == "hybrid":
            if not use_db:
                print("Режим: чистый агентский (без БД) — объекты и планы от агента.")
            else:
                print("Поиск блоков: сначала логика; при частичном результате подключается агент.")
        else:
            print("Поиск логических блоков: логика")
    elif plan_source == "agent":
        print("Планы запросов синтезируются агентом (GigaChat).")
    print("=" * 60)


def build_discovery_runtime_context(
    payload: Dict[str, Any],
    runtime_config_extractor: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> DiscoveryRuntimeContext:
    analysis_mode = payload.get("analysis_mode", "logic")
    plan_source = payload.get("plan_source", "db")
    use_db = bool(payload.get("use_db_connection", True))
    stack = normalize_stack(payload.get("stack"))
    runtime_descriptor = get_runtime_descriptor(stack, "agent" if (analysis_mode == "hybrid" and not use_db) else analysis_mode)
    cluster_config = ClusterConfig(
        segments=payload.get("segments", 120),
        ram_per_seg_gb=payload.get("ram_per_seg_gb", 153.6),
    )
    runtime_analysis_config = runtime_config_extractor(payload)
    analyzer = create_runtime_analyzer(stack, cluster_config, runtime_analysis_config)
    return DiscoveryRuntimeContext(
        analysis_mode=analysis_mode,
        plan_source=plan_source,
        use_db=use_db,
        stack=stack,
        runtime_descriptor=runtime_descriptor,
        cluster_config=cluster_config,
        runtime_analysis_config=runtime_analysis_config,
        analyzer=analyzer,
    )


def build_analysis_runtime_context(
    job: Dict[str, Any],
    *,
    credentials_resolver: Callable[[], Any],
    scope_resolver: Callable[[], Any],
) -> AnalysisRuntimeContext:
    analysis_mode = job.get("analysis_mode", "logic")
    plan_source = job.get("plan_source", "db")
    use_db = bool(job.get("use_db_connection", True))
    stack = normalize_stack(job.get("stack"))
    runtime_descriptor = get_runtime_descriptor(stack, "agent" if (analysis_mode == "hybrid" and not use_db) else analysis_mode)
    analyzer = job["analyzer"]
    agent_credentials = job.get("agent_credentials") or credentials_resolver()
    agent_scope = job.get("agent_scope") or scope_resolver()
    return AnalysisRuntimeContext(
        analysis_mode=analysis_mode,
        plan_source=plan_source,
        use_db=use_db,
        stack=stack,
        runtime_descriptor=runtime_descriptor,
        analyzer=analyzer,
        agent_credentials=agent_credentials,
        agent_scope=agent_scope,
    )
