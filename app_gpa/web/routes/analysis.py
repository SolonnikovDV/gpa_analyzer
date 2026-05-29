"""Analysis page routes and job-worker functions.

This blueprint owns all detailed-analysis pages, job execution, and the
SSE log stream.  Heavy logic lives in module-level private helpers below
the route definitions to keep the route functions thin.
"""
from __future__ import annotations

import hashlib
import io
import time
import traceback
from contextlib import redirect_stdout
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, Response, g, redirect, render_template, request, url_for

from modules.analysis.analysis_handlers import (
    build_analysis_runtime_context,
    build_discovery_runtime_context,
    log_runtime_execution_banner,
)
from modules.analysis.api_contracts import api_error, api_ok
from modules.analysis.detailed_analyzer import DetailedGreenplumFunctionAnalyzer
from modules.analysis.job_contracts import (
    JOB_STATUS_DONE,
    JOB_STATUS_ERROR,
    JOB_STATUS_NOT_FOUND,
    JOB_STATUS_RUNNING,
    JOB_STATUS_TABLES_DISCOVERED,
)
from modules.analysis.observability import log_event
from modules.analysis.runtime_registry import normalize_stack
from core.settings import settings
from web.context import (
    EVENT_JOB_DISCOVERY_COMPLETED,
    JOB_NOT_FOUND_MESSAGE,
    STANDS,
    _agent_chat_model_from,
    _agent_credentials,
    _agent_embedding_model_from,
    _agent_multi_agent_from,
    _agent_provider_from,
    _agent_scope,
    _agent_stack_from,
    _analysis_llm_budget_allows,
    _analysis_orchestrator,
    _build_conn_string,
    _effective_loader_mode,
    _ensure_event_loop,
    _enqueue_log,
    _extract_runtime_analysis_config,
    _governance_template_context,
    _job_runner,
    _job_service,
    _mask_secret,
    _performance_monitors,
    _resolve_agent_credentials,
    _stream_stdout_to_queue,
)

bp = Blueprint("analysis", __name__)


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@bp.route("/detailed")
def detailed_index():
    """Страница ввода DDL."""
    error = request.args.get("error", "")
    stand_hosts = {k: v.get("host") for k, v in STANDS.items() if v.get("host")}
    return render_template("detailed_input.html", stands=STANDS, stand_hosts=stand_hosts, error=error)


@bp.route("/detailed/discover", methods=["POST"])
def detailed_discover():
    """Запуск первого этапа — обнаружение таблиц."""
    ddl = request.form.get("ddl")
    stack = normalize_stack(request.form.get("stack"))
    pure_agent_mode = request.form.get("pure_agent_mode") == "1" or request.form.get("pure_agent") == "on"
    use_db = False if pure_agent_mode else (request.form.get("use_db_connection") == "on")

    use_hybrid = request.form.get("use_hybrid") == "on"
    analysis_mode = "hybrid" if (use_hybrid or pure_agent_mode) else "logic"
    plan_source = "agent" if analysis_mode == "hybrid" else "db"

    form_provider = _agent_provider_from({"agent_provider": request.form.get("agent_provider")})
    if analysis_mode == "hybrid":
        form_creds_raw = (request.form.get("agent_credentials") or "").strip()
        creds = _resolve_agent_credentials(
            form_provider,
            override=form_creds_raw or None,
            use_env=not form_creds_raw,
        )
        if not creds:
            return redirect(url_for("analysis.detailed_index", error="agent_key_required"))

    agent_description = (request.form.get("agent_description") or "").strip()
    form_creds = (request.form.get("agent_credentials") or "").strip()
    form_scope = (request.form.get("agent_scope") or "").strip()
    form_chat_model = (request.form.get("agent_chat_model") or "").strip()
    form_emb_model = (request.form.get("agent_embedding_model") or "").strip()
    data: Dict[str, Any] = {
        "stack": stack,
        "ddl": ddl,
        "agent_description": agent_description,
        "use_db_connection": use_db,
        "segments": int(request.form.get("segments", 120)),
        "ram_per_seg_gb": float(request.form.get("ram_per_seg_gb", 153.6)),
        "analysis_mode": analysis_mode,
        "plan_source": plan_source,
        "agent_provider": form_provider,
        "agent_multi_agent": request.form.get("agent_multi_agent") == "1",
        "agent_credentials": _resolve_agent_credentials(
            form_provider,
            override=form_creds or None,
            use_env=not form_creds,
        ),
        "agent_scope": _agent_scope(form_scope),
        "agent_chat_model": form_chat_model or None,
        "agent_embedding_model": form_emb_model or None,
    }

    if stack == "spark":
        data.update({
            "catalog": (request.form.get("catalog") or "").strip() or None,
            "namespace": (request.form.get("namespace") or "").strip() or None,
            "executor_instances": request.form.get("executor_instances") or 4,
            "executor_cores": request.form.get("executor_cores") or 4,
            "executor_memory": (request.form.get("executor_memory") or "").strip() or "8g",
            "spark_metadata_json": (request.form.get("spark_metadata_json") or "").strip() or None,
            "spark_profile_json": (request.form.get("spark_profile_json") or "").strip() or None,
        })
    elif stack == "pyspark":
        data.update({
            "session_name": (request.form.get("pyspark_session_name") or request.form.get("session_name") or "").strip() or None,
            "pyspark_executor_instances": request.form.get("pyspark_executor_instances") or 4,
            "pyspark_executor_memory": (request.form.get("pyspark_executor_memory") or "").strip() or "8g",
            "pyspark_metadata_json": (request.form.get("pyspark_metadata_json") or "").strip() or None,
            "pyspark_profile_json": (request.form.get("pyspark_profile_json") or "").strip() or None,
        })

    if not ddl or not ddl.strip():
        return redirect(url_for("analysis.detailed_index", error="ddl_required"))

    if use_db:
        if stack == "greenplum":
            user = request.form.get("user", "").strip()
            password = request.form.get("password", "").strip()
            if not user or not password:
                return redirect(url_for("analysis.detailed_index", error="db_required"))
            data.update({
                "stand_type": request.form.get("stand_type", "PROM"),
                "host": request.form.get("host") or None,
                "port": request.form.get("port") or None,
                "dbname": request.form.get("dbname") or None,
                "user": user,
                "password": password,
            })
        elif stack == "spark":
            master_url = (request.form.get("master_url") or "").strip()
            if not master_url:
                return redirect(url_for("analysis.detailed_index", error="db_required"))
            data.update({
                "master_url": master_url,
                "spark_user": (request.form.get("spark_user") or "").strip() or None,
                "spark_password": (request.form.get("spark_password") or "").strip() or None,
            })
        else:
            master_url = (request.form.get("pyspark_master_url") or "").strip()
            if not master_url:
                return redirect(url_for("analysis.detailed_index", error="db_required"))
            data.update({
                "master_url": master_url,
                "pyspark_user": (request.form.get("pyspark_user") or "").strip() or None,
                "pyspark_password": (request.form.get("pyspark_password") or "").strip() or None,
            })

    job_id = datetime.now().strftime("%Y%m%d%H%M%S%f") + "_disc"
    _analysis_orchestrator.create_discovery_job(job_id, {
        "status": JOB_STATUS_RUNNING,
        "stack": stack,
        "ddl": ddl,
        "execution_backend": settings.job_runner_backend,
        "request_id": getattr(g, "request_id", None),
        "discovery_result": None,
        "analysis_mode": analysis_mode,
        "plan_source": plan_source,
        "use_db_connection": use_db,
        "agent_credentials": data["agent_credentials"],
        "agent_scope": data["agent_scope"],
        "agent_provider": data.get("agent_provider"),
        "agent_multi_agent": data.get("agent_multi_agent"),
        "agent_chat_model": data.get("agent_chat_model"),
        "agent_embedding_model": data.get("agent_embedding_model"),
        "segments": data.get("segments"),
        "ram_per_seg_gb": data.get("ram_per_seg_gb"),
        "master_url": data.get("master_url"),
        "catalog": data.get("catalog"),
        "namespace": data.get("namespace"),
        "session_name": data.get("session_name"),
        "executor_instances": data.get("executor_instances"),
        "executor_cores": data.get("executor_cores"),
        "executor_memory": data.get("executor_memory"),
        "pyspark_executor_instances": data.get("pyspark_executor_instances"),
        "pyspark_executor_memory": data.get("pyspark_executor_memory"),
        "spark_metadata_json": data.get("spark_metadata_json"),
        "spark_profile_json": data.get("spark_profile_json"),
        "pyspark_metadata_json": data.get("pyspark_metadata_json"),
        "pyspark_profile_json": data.get("pyspark_profile_json"),
    })
    log_event(
        "job.discovery.created",
        request_id=getattr(g, "request_id", None),
        job_id=job_id,
        stack=stack,
        analysis_mode=analysis_mode,
        use_db_connection=use_db,
    )

    run_handle = _job_runner.start(_run_discovery_job, job_id, data)
    _job_service.update_job(
        job_id,
        execution_backend=run_handle.backend,
        execution_run_id=run_handle.run_id,
    )
    log_event(
        "job.discovery.enqueued",
        request_id=getattr(g, "request_id", None),
        job_id=job_id,
        backend=run_handle.backend,
        execution_run_id=run_handle.run_id,
    )
    return redirect(url_for("analysis.discovery_result", job_id=job_id))


@bp.route("/discovery/result/<job_id>")
def discovery_result(job_id: str):
    """Страница с результатами обнаружения таблиц."""
    job = _job_service.get_job(job_id)
    if not job:
        return JOB_NOT_FOUND_MESSAGE, 404
    mode = job.get("analysis_mode", "logic")
    use_db = job.get("use_db_connection", True)
    loader_mode = _effective_loader_mode(mode, use_db)
    gov = _governance_template_context()
    return render_template(
        "table_sizes.html",
        job_id=job_id,
        status=job["status"],
        loader_mode=loader_mode,
        stack=job.get("stack", "greenplum"),
        agent_chat_model=job.get("agent_chat_model") or "",
        agent_embedding_model=job.get("agent_embedding_model") or "",
        agent_provider=job.get("agent_provider") or "gigachat",
        agent_multi_agent=bool(job.get("agent_multi_agent")),
        **gov,
    )


@bp.route("/detailed/analyze", methods=["POST"])
def detailed_analyze():
    """Запуск второго этапа — анализ с пользовательскими размерами."""
    job_id = request.form.get("job_id")

    job = _job_service.get_job(job_id)
    if not job:
        return api_error("job_not_found", JOB_NOT_FOUND_MESSAGE, http_status=404)

    params_str = request.form.get("params", "").strip()
    params = [p.strip() for p in params_str.split(",") if p.strip()] if params_str else []

    print(f"DEBUG: Получены параметры для анализа из формы: {params}")

    _analysis_orchestrator.store_analysis_params(job_id, params)
    if job.get("discovery_result"):
        print(f"Сохранены параметры в discovery_result: {params}")

    analyzer = job.get("analyzer")
    if not analyzer:
        return redirect(url_for("analysis.detailed_index", error="job_restore_requires_restart"))
    analyzer.reset_for_rerun()
    print(f"🔄 Состояние анализатора сброшено для job_id: {job_id}")

    _analysis_orchestrator.prepare_analysis_run(job_id, _agent_credentials, _agent_scope)

    user_sizes: Dict[str, int] = {}
    for key in request.form:
        if key.startswith("size_"):
            raw_name = key[5:]
            table_name = raw_name.replace("___DOT___", ".")
            try:
                val_str = request.form.get(key, "").strip()
                value = int(val_str) if val_str else 0
                if value >= 0:
                    user_sizes[table_name] = value
            except ValueError:
                pass

    print(f"DEBUG: Получены пользовательские размеры: {len(user_sizes)} таблиц")
    if user_sizes:
        for t, v in list(user_sizes.items())[:10]:
            print(f"  {t}: {v:,} строк")
        if len(user_sizes) > 10:
            print(f"  ... и ещё {len(user_sizes) - 10}")

    _analysis_orchestrator.start_performance_monitor(job_id)
    log_event(
        "job.analysis.started",
        request_id=job.get("request_id"),
        job_id=job_id,
        params_count=len(params),
        user_sizes_count=len(user_sizes),
    )

    run_handle = _job_runner.start(_run_analysis_job, job_id, {"params": params, "user_sizes": user_sizes})
    _job_service.update_job(
        job_id,
        execution_backend=run_handle.backend,
        execution_run_id=run_handle.run_id,
    )
    log_event(
        "job.analysis.enqueued",
        request_id=job.get("request_id"),
        job_id=job_id,
        backend=run_handle.backend,
        execution_run_id=run_handle.run_id,
    )

    job = _job_service.require_job(job_id)
    mode = job.get("analysis_mode", "logic")
    use_db = job.get("use_db_connection", True)
    loader_mode = _effective_loader_mode(mode, use_db)
    return redirect(url_for("analysis.detailed_result", job_id=job_id) + f"?mode={loader_mode}")


@bp.route("/detailed/result/<job_id>")
def detailed_result(job_id: str):
    """Страница с результатами анализа."""
    job = _job_service.get_job(job_id)
    if not job:
        return JOB_NOT_FOUND_MESSAGE, 404
    mode = request.args.get("mode")
    if not mode:
        m = job.get("analysis_mode", "logic")
        use_db = job.get("use_db_connection", True)
        mode = _effective_loader_mode(m, use_db)
    return render_template(
        "detailed_result.html",
        job_id=job_id,
        status=job["status"],
        loader_mode=mode,
        stack=job.get("stack", "greenplum"),
        agent_chat_model=job.get("agent_chat_model") or "",
        agent_embedding_model=job.get("agent_embedding_model") or "",
        agent_provider=job.get("agent_provider") or "gigachat",
        agent_multi_agent=bool(job.get("agent_multi_agent")),
        **_governance_template_context(),
    )


@bp.route("/stream/<job_id>")
def stream(job_id: str):
    """Server-Sent Events поток логов."""
    if not _job_service.has_log_queue(job_id) and not _job_service.get_job(job_id):
        return "Лог не найден", 404

    def event_stream():
        job = _job_service.get_job(job_id) or {}
        execution_backend = job.get("execution_backend") or settings.job_runner_backend
        q = _job_service.get_log_queue(job_id)
        if q is not None and execution_backend == "thread":
            while True:
                line = q.get()
                yield f"data: {line}\n\n"
                if line.strip() == "[STREAM_END]":
                    break
            return

        sent_lines = 0
        while True:
            lines = _job_service.read_persisted_logs(job_id)
            while sent_lines < len(lines):
                line = lines[sent_lines]
                sent_lines += 1
                yield f"data: {line}\n\n"
                if line.strip() == "[STREAM_END]":
                    return
            current_job = _job_service.get_job(job_id)
            if current_job and current_job.get("status") in (JOB_STATUS_DONE, JOB_STATUS_ERROR):
                yield "data: [STREAM_END]\n\n"
                return
            time.sleep(0.5)

    return Response(event_stream(), mimetype="text/event-stream")


@bp.route("/status/<job_id>")
def status(job_id: str):
    """Возвращает статус задачи."""
    job = _job_service.get_job(job_id)
    if not job:
        return api_error("job_not_found", JOB_NOT_FOUND_MESSAGE, http_status=404, job_status=JOB_STATUS_NOT_FOUND)

    st = job["status"]
    res: Dict[str, Any] = {
        "status": st,
        "request_id": job.get("request_id"),
        "stack": job.get("stack", "greenplum"),
        "analysis_mode": job.get("analysis_mode", "logic"),
        "use_db_connection": job.get("use_db_connection", False),
        "agent_chat_model": job.get("agent_chat_model") or "",
        "agent_embedding_model": job.get("agent_embedding_model") or "",
        "agent_provider": job.get("agent_provider") or "gigachat",
        "agent_multi_agent": bool(job.get("agent_multi_agent")),
        "execution_backend": job.get("execution_backend"),
        "execution_run_id": job.get("execution_run_id"),
    }
    res.update(_governance_template_context())

    if "discovery_result" in job and job["discovery_result"]:
        res["use_agent_path"] = job["discovery_result"].get("use_agent_path", False)

    if st == JOB_STATUS_TABLES_DISCOVERED and job.get("discovery_result"):
        res["discovery"] = job["discovery_result"]

    if st == JOB_STATUS_DONE and job.get("result"):
        jr = job["result"]
        fn = jr.get("function")
        in_type = jr.get("input_type")
        try:
            from modules.analysis.object_display import resolve_object_display_label
            object_display = jr.get("object_display") or resolve_object_display_label(in_type, fn, job.get("ddl") or "")
        except Exception:
            object_display = fn
        res["summary"] = {
            "function": fn,
            "input_type": in_type,
            "object_display": object_display,
            "blocks_analyzed": jr.get("analyzed_blocks", 0),
            "blocks_count": jr.get("blocks_count", 0),
            "total_memory_gb": jr.get("total_memory_gb", 0),
            "antipattern_added_gb": jr.get("antipattern_added_gb", 0),
            "estimated_time_sec": jr.get("estimated_time_sec", 0),
            "max_utilization": jr.get("max_utilization", 0),
            "memory_pressure": jr.get("memory_pressure"),
            "cluster_capacity_gb": jr.get("cluster_capacity_gb"),
            "risk": jr.get("risk", "N/A"),
        }

    if job.get("error"):
        res["error"] = job["error"]

    return api_ok(data=res, **res)


@bp.route("/details/<job_id>")
def details(job_id: str):
    """Возвращает полные результаты анализа в JSON."""
    job = _job_service.get_job(job_id)
    if not job or job["status"] != JOB_STATUS_DONE:
        return api_error("result_unavailable", "Результат недоступен", http_status=400)
    out = dict(job["result"])
    out["request_id"] = job.get("request_id")
    out["stack"] = job.get("stack", "greenplum")
    out["analysis_mode"] = job.get("analysis_mode", "logic")
    out["use_db_connection"] = job.get("use_db_connection", False)
    return api_ok(data=out, **out)


@bp.route("/performance/<job_id>")
def get_performance(job_id: str):
    """Возвращает статистику производительности."""
    monitor = _performance_monitors.get(job_id)
    if not monitor:
        return api_error("performance_monitor_not_found", "Монитор не найден", http_status=404)
    stats = monitor.get_stats()
    return api_ok(data=stats, **stats)


# ---------------------------------------------------------------------------
# Analysis-specific helpers
# ---------------------------------------------------------------------------

def _apply_runtime_quality_metadata(
    result: Dict[str, Any],
    *,
    stack: str,
    runtime_descriptor: Any,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    if stack == "greenplum":
        segments = payload.get("segments")
        ram_per_seg_gb = payload.get("ram_per_seg_gb")
        try:
            cluster_capacity_gb = float(segments) * float(ram_per_seg_gb) * 0.72
        except (TypeError, ValueError):
            cluster_capacity_gb = 0.0
        result.setdefault("runtime_context", {
            "runtime_label": runtime_descriptor.ui.get("stack_label", stack),
            "quality": "deep",
            "capacity_gb": round(cluster_capacity_gb, 3),
            "notes": ["GreenPlum path использует нативный analyzer и DB-backed discovery/analyze flow."],
        })
        result.setdefault("analysis_quality", "deep")
        result.setdefault("cluster_capacity_gb", round(cluster_capacity_gb, 3))
        total_memory_gb = float(result.get("total_memory_gb") or 0.0)
        result.setdefault(
            "memory_pressure",
            round(total_memory_gb / cluster_capacity_gb, 3) if cluster_capacity_gb > 0 else None,
        )
        return result

    result.setdefault("runtime_context", {
        "runtime_label": runtime_descriptor.ui.get("stack_label", stack),
        "quality": "approximate",
        "notes": ["Для этого стека используется runtime-hinted analysis без нативного коннектора."],
    })
    result.setdefault("analysis_quality", result.get("runtime_context", {}).get("quality", "approximate"))
    result.setdefault("cluster_capacity_gb", 0.0)
    result.setdefault("memory_pressure", None)
    return result


def _collect_logic_warning_fragments(
    analyzer: DetailedGreenplumFunctionAnalyzer, source_text: str
) -> Dict[str, Any]:
    from modules.analysis import block_parser

    sql_markers = (
        "SELECT ", "INSERT ", "UPDATE ", "DELETE ", "MERGE ", "WITH ",
        "EXECUTE ", "RETURN QUERY", "CREATE TEMP", "TRUNCATE ",
    )
    warnings: List[str] = []
    fragments: List[str] = []
    executable_count = 0

    blocks = list(getattr(analyzer, "blocks", []) or [])
    block_types = list(getattr(analyzer, "block_types", []) or [])

    for idx, block in enumerate(blocks):
        block_type = block_types[idx] if idx < len(block_types) else "OTHER"
        if block_parser.is_executable_sql(block_type):
            executable_count += 1
            continue
        block_text = str(block or "").strip()
        compact_upper = " ".join(block_text.upper().split())
        if block_text and any(marker in compact_upper for marker in sql_markers):
            warnings.append(
                f"Логика пометила фрагмент {idx + 1} как {block_type}; он передан агенту на валидацию логического блока."
            )
            fragments.append(block_text)

    if executable_count == 0:
        warnings.insert(0, "Логика не выделила исполняемые логические блоки; включён агентский fallback.")
        fallback_text = str(source_text or "").strip()
        if fallback_text and not fragments:
            fragments.append(fallback_text)

    return {"warnings": warnings, "fragments": fragments, "executable_count": executable_count}


def _merge_agent_objects_into_discovery(
    analyzer: DetailedGreenplumFunctionAnalyzer,
    result: Dict[str, Any],
    agent_objects: List[str],
) -> int:
    if not analyzer.conn:
        return 0

    discovered_tables = getattr(analyzer, "discovered_tables", {}) or {}
    view_to_tables_map = getattr(analyzer, "view_to_tables_map", {}) or {}
    physical_tables = getattr(analyzer, "physical_tables", set()) or set()
    added = 0

    for full_name in agent_objects or []:
        raw_name = str(full_name or "").strip()
        if not raw_name:
            continue
        if "." in raw_name:
            schema, table = raw_name.split(".", 1)
        else:
            schema, table = "public", raw_name
        schema = schema.strip().lower()
        table = table.strip().lower()
        if not table:
            continue

        resolved = analyzer._resolve_object_to_tables(schema, table) or set()
        if not resolved:
            resolved = {(schema, table)}

        view_key = f"{schema}.{table}"
        view_to_tables_map.setdefault(view_key, [f"{s}.{t}" for s, t in sorted(resolved)])

        for phys_schema, phys_table in resolved:
            physical_tables.add((phys_schema, phys_table))
            key = f"{phys_schema}.{phys_table}"
            if key in discovered_tables:
                continue
            stats = analyzer._get_real_table_stats(phys_schema, phys_table)
            if stats:
                discovered_tables[key] = {
                    "schema": phys_schema, "table": phys_table,
                    "current_rows": stats.rows_estimate, "size_gb": stats.memory_estimate_gb,
                    "avg_row_size_bytes": stats.avg_row_size_bytes, "columns": stats.columns,
                    "user_rows": stats.rows_estimate,
                }
            else:
                discovered_tables[key] = {
                    "schema": phys_schema, "table": phys_table,
                    "current_rows": 0, "size_gb": 0.0,
                    "avg_row_size_bytes": 0, "columns": 0, "user_rows": 0,
                }
            added += 1

    analyzer.discovered_tables = discovered_tables
    analyzer.view_to_tables_map = view_to_tables_map
    analyzer.physical_tables = physical_tables
    result["discovered_tables"] = discovered_tables
    result["view_to_tables_map"] = view_to_tables_map
    result["physical_tables_count"] = len(physical_tables)
    return added


def _apply_hybrid_agent_validation(
    analyzer: DetailedGreenplumFunctionAnalyzer,
    result: Dict[str, Any],
    payload: Dict[str, Any],
) -> None:
    if payload.get("analysis_mode") != "hybrid" or not payload.get("use_db_connection"):
        return

    warning_payload = _collect_logic_warning_fragments(analyzer, payload.get("ddl", ""))
    logic_warnings = warning_payload.get("warnings") or []
    if not logic_warnings:
        return

    result["logic_warnings"] = logic_warnings
    result["agent_validated_fragments"] = len(warning_payload.get("fragments") or [])
    print("⚠️ Гибрид: обнаружены предупреждённые фрагменты логики")
    for message in logic_warnings:
        print(f"   • {message}")

    creds = payload.get("agent_credentials") or _agent_credentials()
    if not creds:
        print("⚠️ Гибрид: agent fallback недоступен, ключ GigaChat не задан")
        return
    if not _analysis_llm_budget_allows("blocks_assist", result):
        return

    try:
        from modules.agents.gigachat_agent import get_blocks_and_objects_from_ddl

        fragment_source = "\n\n".join(warning_payload.get("fragments") or []) or payload.get("ddl", "")
        agent_data = get_blocks_and_objects_from_ddl(
            fragment_source,
            credentials_override=creds,
            scope_override=payload.get("agent_scope") or _agent_scope(),
            model_override=_agent_chat_model_from(payload),
            stack=_agent_stack_from(payload),
            provider=_agent_provider_from(payload),
            multi_agent=_agent_multi_agent_from(payload),
        ) or {}
        validated_blocks = agent_data.get("blocks") or []
        replace_logic_blocks = warning_payload.get("executable_count", 0) == 0

        if validated_blocks:
            normalized_existing = set()
            if replace_logic_blocks:
                analyzer.blocks = []
                analyzer.block_types = []
            else:
                normalized_existing = {
                    " ".join(str(block).split()).lower()
                    for block in (getattr(analyzer, "blocks", []) or [])
                    if str(block or "").strip()
                }

            added_blocks = 0
            for block_info in validated_blocks:
                sql = str((block_info or {}).get("sql") or "").strip()
                if not sql:
                    continue
                normalized = " ".join(sql.split()).lower()
                if not replace_logic_blocks and normalized in normalized_existing:
                    continue
                analyzer.blocks.append(sql)
                analyzer.block_types.append(str((block_info or {}).get("type") or "OTHER"))
                normalized_existing.add(normalized)
                added_blocks += 1

            if added_blocks:
                print(f"🤖 Гибрид: агент подтвердил/добавил {added_blocks} логических блоков")
                result["blocks_count"] = len(analyzer.blocks)
                result["block_types"] = analyzer.block_types
                result["use_agent_path"] = True

        merged_objects = _merge_agent_objects_into_discovery(analyzer, result, agent_data.get("objects") or [])
        if merged_objects:
            print(f"🤖 Гибрид: добавлено объектов из агентной валидации: {merged_objects}")
            result["use_agent_path"] = True
            result["objects_referenced_in_blocks"] = max(
                int(result.get("objects_referenced_in_blocks", 0) or 0),
                len(agent_data.get("objects") or []),
            )
    except ImportError as e:
        print(f"⚠️ Гибрид: agent fallback недоступен ({e})")
    except Exception as e:
        print(f"⚠️ Гибрид: ошибка agent fallback для предупреждённых фрагментов: {e}")


def _enrich_discovery_metadata(result: Dict[str, Any], ddl: str) -> None:
    try:
        from analysis_pipeline.orchestrator import discovery_attachment_for_result
        from llm.tracker import tracker_snapshot

        result["parser_first_pass"] = discovery_attachment_for_result(ddl or "")
        result["llm_roundtrips_in_phase"] = tracker_snapshot()
    except Exception as exc:
        result["parser_first_pass"] = {"error": str(exc)}
        result["llm_roundtrips_in_phase"] = {
            "chat_completions": 0,
            "tracker_active": False,
            "error": str(exc),
        }


def _finalize_discovery(job_id: str, analyzer: Any, result: Dict[str, Any], payload: Dict[str, Any]) -> None:
    _enrich_discovery_metadata(result, str(payload.get("ddl") or ""))
    _analysis_orchestrator.set_discovery_result(job_id, analyzer, result)


# ---------------------------------------------------------------------------
# Worker functions (run in job runner threads / queue workers)
# ---------------------------------------------------------------------------

def _run_discovery_job(job_id: str, payload: Dict[str, Any]) -> None:
    """Запуск первого этапа: обнаружение таблиц."""
    _ensure_event_loop()
    try:
        from llm.tracker import tracker_reset
        tracker_reset()
    except Exception:
        pass
    buf = _stream_stdout_to_queue(job_id)
    log_event(
        "job.discovery.worker_started",
        request_id=payload.get("request_id"),
        job_id=job_id,
        stack=payload.get("stack"),
    )
    try:
        with redirect_stdout(buf):
            context = build_discovery_runtime_context(payload, _extract_runtime_analysis_config)
            analysis_mode = context.analysis_mode
            plan_source = context.plan_source
            use_db = context.use_db
            stack = context.stack
            runtime_descriptor = context.runtime_descriptor
            runtime_analysis_config = context.runtime_analysis_config
            analyzer = context.analyzer
            log_runtime_execution_banner(
                stack_label=runtime_descriptor.ui.get("stack_label", stack),
                analysis_mode=analysis_mode,
                plan_source=plan_source,
                use_db=use_db,
                phase="discovery",
                agent_chat_model=_agent_chat_model_from(payload),
                agent_embedding_model=_agent_embedding_model_from(payload),
            )

            if stack != "greenplum":
                result = analyzer.discover_tables(payload["ddl"])
                result = _apply_runtime_quality_metadata(
                    result, stack=stack, runtime_descriptor=runtime_descriptor, payload=payload
                )
                result["stack"] = stack
                result["runtime_label"] = runtime_descriptor.ui.get("stack_label", stack)
                result["runtime_config_used"] = runtime_analysis_config
                result["agent_requested_ddl"] = []
                _finalize_discovery(job_id, analyzer, result, payload)
                log_event(
                    EVENT_JOB_DISCOVERY_COMPLETED,
                    request_id=payload.get("request_id"),
                    job_id=job_id,
                    stack=stack,
                    discovered_objects=len(result.get("discovered_tables", {}) or {}),
                )
                return

            is_pure_agent = not use_db and payload.get("analysis_mode") == "hybrid"
            if is_pure_agent:
                ddl_hash = hashlib.sha256((payload.get("ddl") or "").encode("utf-8")).hexdigest()
                desc_hash = hashlib.sha256((payload.get("agent_description") or "").encode("utf-8")).hexdigest()
                try:
                    from modules.agents.agent_cache_db import get_state, set_state, state_key_discovery
                    state_key = state_key_discovery(ddl_hash, use_db, desc_hash)
                    cached = get_state(state_key)
                    if cached and cached.get("use_agent_path") and cached.get("discovered_tables") and cached.get("blocks"):
                        analyzer.blocks = cached["blocks"]
                        analyzer.block_types = cached["block_types"]
                        analyzer.input_type = cached.get("input_type", "function")
                        analyzer.discovered_tables = cached["discovered_tables"]
                        analyzer.view_to_tables_map = cached.get("view_to_tables_map") or {}
                        analyzer.variables = cached.get("variables") or {}
                        analyzer.function_params = cached.get("function_params") or []
                        analyzer.func_name = cached.get("function", "unknown")
                        analyzer.temp_tables = set(cached.get("temp_tables") or [])
                        analyzer.physical_tables = set(tuple(p) for p in (cached.get("physical_tables") or []))
                        result = {k: cached[k] for k in (
                            "input_type", "function", "blocks_count", "block_types", "temp_tables",
                            "discovered_tables", "view_to_tables_map", "physical_tables_count",
                            "objects_referenced_in_blocks", "variables", "status",
                        ) if k in cached}
                        result["agent_requested_ddl"] = cached.get("agent_requested_ddl") or []
                        result["use_agent_path"] = True
                        print("📦 [Чистый агент] Использован кэш (блоки и объекты от агента)")
                        _finalize_discovery(job_id, analyzer, result, payload)
                        log_event(
                            EVENT_JOB_DISCOVERY_COMPLETED,
                            request_id=payload.get("request_id"),
                            job_id=job_id,
                            stack=stack,
                            discovered_objects=len(result.get("discovered_tables", {}) or {}),
                            source="cache",
                        )
                        return
                except Exception:
                    pass

                creds = payload.get("agent_credentials") or _agent_credentials()
                if creds:
                    if not _analysis_llm_budget_allows("blocks_assist", result=None):
                        _analysis_orchestrator.fail_job(
                            job_id,
                            "Чистый агентский режим: превышен лимит LLM-вызовов для анализа.",
                        )
                        return
                    try:
                        from modules.agents.gigachat_agent import get_blocks_and_objects_from_ddl
                        agent_data = get_blocks_and_objects_from_ddl(
                            payload["ddl"],
                            credentials_override=creds,
                            scope_override=payload.get("agent_scope") or _agent_scope(),
                            model_override=_agent_chat_model_from(payload),
                            stack=_agent_stack_from(payload),
                            provider=_agent_provider_from(payload),
                            multi_agent=_agent_multi_agent_from(payload),
                        )
                        if agent_data and (agent_data.get("blocks") or agent_data.get("objects")):
                            blocks_list = agent_data.get("blocks") or []
                            objects_list = agent_data.get("objects") or []
                            function_params_list = agent_data.get("function_params") or []
                            variables_list = agent_data.get("variables") or []
                            analyzer.blocks = [b.get("sql", "") for b in blocks_list if b.get("sql")]
                            analyzer.block_types = [b.get("type", "OTHER") for b in blocks_list if b.get("sql")]
                            analyzer.input_type = "function"
                            analyzer.func_name = "unknown"
                            analyzer.function_params = [str(p) for p in function_params_list if p]
                            analyzer.variables = {str(v): "" for v in variables_list if v}
                            analyzer.view_to_tables_map = {}
                            analyzer.temp_tables = {t for t in objects_list if isinstance(t, str) and "." not in t.strip()}
                            analyzer.physical_tables = set()
                            agent_tables: Dict[str, Any] = {}
                            for full_name in objects_list:
                                full_name = str(full_name).strip()
                                if not full_name:
                                    continue
                                if "." in full_name:
                                    parts = full_name.split(".", 1)
                                    schema, table = parts[0].strip(), parts[1].strip()
                                else:
                                    schema, table = "public", full_name
                                agent_tables[full_name] = {
                                    "schema": schema, "table": table, "current_rows": 0, "size_gb": 0.0,
                                    "avg_row_size_bytes": 0, "columns": 0, "user_rows": 0,
                                }
                            analyzer.discovered_tables = agent_tables
                            result = {
                                "input_type": "function", "function": analyzer.func_name,
                                "blocks_count": len(analyzer.blocks), "block_types": analyzer.block_types,
                                "temp_tables": list(analyzer.temp_tables), "discovered_tables": agent_tables,
                                "view_to_tables_map": {}, "physical_tables_count": len(objects_list),
                                "objects_referenced_in_blocks": len(objects_list),
                                "variables": analyzer.variables, "function_params": analyzer.function_params,
                                "status": "tables_discovered", "agent_requested_ddl": [], "use_agent_path": True,
                            }
                            print("🤖 [Агент] Чистый агентский режим: блоки и объекты найдены агентом")
                            print(f"   Итого: блоков {len(analyzer.blocks)}, объектов {len(objects_list)}, параметров {len(analyzer.function_params)}, переменных {len(analyzer.variables)}")
                            _finalize_discovery(job_id, analyzer, result, payload)
                            log_event(
                                EVENT_JOB_DISCOVERY_COMPLETED,
                                request_id=payload.get("request_id"),
                                job_id=job_id,
                                stack=stack,
                                discovered_objects=len(agent_tables),
                                source="pure_agent",
                            )
                            try:
                                from modules.agents.agent_cache_db import set_state, state_key_discovery
                                ddl_h = hashlib.sha256((payload.get("ddl") or "").encode("utf-8")).hexdigest()
                                desc_h = hashlib.sha256((payload.get("agent_description") or "").encode("utf-8")).hexdigest()
                                state_key = state_key_discovery(ddl_h, use_db, desc_h)
                                state_to_save = dict(result)
                                state_to_save.update({
                                    "blocks": analyzer.blocks, "view_to_tables_map": {},
                                    "variables": analyzer.variables, "function_params": analyzer.function_params,
                                    "function": analyzer.func_name, "temp_tables": [], "physical_tables": [],
                                    "input_type": "function",
                                })
                                set_state(state_key, state_to_save)
                            except Exception:
                                pass
                            return
                        else:
                            print("⚠️ Чистый агентский режим: агент вернул пустой результат")
                    except ImportError as e:
                        print(f"⚠️ Чистый агентский режим: {e}")
                    except Exception as e:
                        print(f"⚠️ Чистый агентский режим (блоки и объекты): {e}")
                else:
                    print("⚠️ Чистый агентский режим: ключ GigaChat не задан")

                _analysis_orchestrator.fail_job(
                    job_id,
                    "Чистый агентский режим: не удалось получить блоки и объекты от агента. "
                    "Проверьте ключ GigaChat, установите gigachat (pip install gigachat) и повторите. "
                    "Парсер не используется — только агент.",
                )
                return

            ddl_hash = hashlib.sha256((payload.get("ddl") or "").encode("utf-8")).hexdigest()
            desc_hash = hashlib.sha256((payload.get("agent_description") or "").encode("utf-8")).hexdigest()
            try:
                from modules.agents.agent_cache_db import get_state, set_state, state_key_discovery
                state_key = state_key_discovery(ddl_hash, use_db, desc_hash)
                cached = get_state(state_key)
                if is_pure_agent and cached:
                    if not cached.get("discovered_tables") or len(cached.get("discovered_tables") or {}) == 0:
                        cached = None
                if cached and cached.get("discovered_tables") is not None and cached.get("blocks") is not None:
                    analyzer.blocks = cached["blocks"]
                    analyzer.block_types = cached["block_types"]
                    analyzer.input_type = cached.get("input_type") or (
                        "function" if cached.get("use_agent_path") else None
                    )
                    analyzer.discovered_tables = cached["discovered_tables"]
                    analyzer.view_to_tables_map = cached.get("view_to_tables_map") or {}
                    analyzer.variables = cached.get("variables") or {}
                    analyzer.function_params = cached.get("function_params") or []
                    analyzer.func_name = cached.get("function", "unknown")
                    analyzer.temp_tables = set(cached.get("temp_tables") or [])
                    analyzer.physical_tables = set(tuple(p) for p in (cached.get("physical_tables") or []))
                    result = {k: cached[k] for k in (
                        "input_type", "function", "blocks_count", "block_types", "temp_tables",
                        "discovered_tables", "view_to_tables_map", "physical_tables_count",
                        "objects_referenced_in_blocks", "variables", "status",
                    ) if k in cached}
                    result["agent_requested_ddl"] = cached.get("agent_requested_ddl") or []
                    result["use_agent_path"] = cached.get("use_agent_path", False)
                    if use_db:
                        conn = _build_conn_string(
                            payload.get("stand_type", "PROM"),
                            payload["user"], payload["password"],
                            payload.get("host"), payload.get("port"), payload.get("dbname"),
                        )
                        analyzer.connect(conn)
                    print("📦 Использован кэш состояний (discovery без повторного расчёта)")
                    _finalize_discovery(job_id, analyzer, result, payload)
                    return
            except Exception:
                pass

            if use_db:
                conn = _build_conn_string(
                    payload.get("stand_type", "PROM"),
                    payload["user"], payload["password"],
                    payload.get("host"), payload.get("port"), payload.get("dbname"),
                )
                if not analyzer.connect(conn):
                    _analysis_orchestrator.fail_job(job_id, "Не удалось подключиться к БД. Проверьте логин и пароль.")
                    return

            result = analyzer.discover_tables(payload["ddl"])
            result = _apply_runtime_quality_metadata(
                result, stack=stack, runtime_descriptor=runtime_descriptor, payload=payload
            )
            _apply_hybrid_agent_validation(analyzer, result, payload)

            if not use_db and payload.get("analysis_mode") == "hybrid":
                creds = payload.get("agent_credentials") or _agent_credentials()
                if creds:
                    if not _analysis_llm_budget_allows("objects_assist", result):
                        creds = None
                if creds:
                    try:
                        from modules.agents.gigachat_agent import get_objects_from_sql_or_function
                        obj_list = get_objects_from_sql_or_function(
                            payload["ddl"],
                            credentials_override=creds,
                            scope_override=payload.get("agent_scope") or _agent_scope(),
                            model_override=_agent_chat_model_from(payload),
                        )
                        if obj_list:
                            print(f"🤖 [Агент] Гибрид (без БД): объекты найдены — {len(obj_list)} шт.")
                            agent_tables = {}
                            for full_name in obj_list:
                                full_name = str(full_name).strip()
                                if not full_name:
                                    continue
                                if "." in full_name:
                                    parts = full_name.split(".", 1)
                                    schema, table = parts[0].strip(), parts[1].strip()
                                else:
                                    schema, table = "public", full_name
                                agent_tables[full_name] = {
                                    "schema": schema, "table": table, "current_rows": 0, "size_gb": 0.0,
                                    "avg_row_size_bytes": 0, "columns": 0, "user_rows": 0,
                                }
                            result["discovered_tables"] = agent_tables
                            result["status"] = "tables_discovered"
                            result["use_agent_path"] = True
                            analyzer.discovered_tables = agent_tables
                            result["agent_requested_ddl"] = []
                    except ImportError as e:
                        print(f"⚠️ Чистый агентский режим (извлечение объектов): {e}")
                    except Exception as e:
                        print(f"⚠️ Чистый агентский режим (извлечение объектов): {e}")
                else:
                    print("⚠️ Чистый агентский режим: ключ GigaChat не задан")

            if payload.get("analysis_mode") == "hybrid":
                try:
                    from modules.agents.gigachat_agent import get_missing_objects_for_ddl
                    found_objects = list(result.get("discovered_tables", {}).keys())
                    creds = payload.get("agent_credentials") or _agent_credentials()
                    if creds and _analysis_llm_budget_allows("objects_assist", result):
                        missing = get_missing_objects_for_ddl(
                            payload["ddl"],
                            found_objects,
                            credentials_override=creds,
                            scope_override=payload.get("agent_scope") or _agent_scope(),
                            model_override=_agent_chat_model_from(payload),
                        )
                        result["agent_requested_ddl"] = missing
                        if missing:
                            print(f"📋 [Агент] Гибрид: запрос DDL для недостающих объектов: {missing}")
                    else:
                        result["agent_requested_ddl"] = []
                    ref_in_blocks = result.get("objects_referenced_in_blocks", 0)
                    discovered_count = len(result.get("discovered_tables", {}))
                    if discovered_count == 0 or (ref_in_blocks > 0 and discovered_count < ref_in_blocks):
                        result["use_agent_path"] = True
                        print(f"📋 [Агент] Гибрид: включён агентский путь")
                except ImportError as e:
                    result["agent_requested_ddl"] = []
                    print(f"⚠️ Гибрид: не установлен пакет ({e})")
                except Exception as e:
                    result["agent_requested_ddl"] = []
                    print(f"⚠️ Проверка недостающих объектов агентом: {e}")
            else:
                result["agent_requested_ddl"] = []

            _finalize_discovery(job_id, analyzer, result, payload)
            log_event(
                EVENT_JOB_DISCOVERY_COMPLETED,
                request_id=payload.get("request_id"),
                job_id=job_id,
                stack=stack,
                discovered_objects=len(result.get("discovered_tables", {}) or {}),
            )

            try:
                from modules.agents.agent_cache_db import set_state, state_key_discovery
                if not use_db and payload.get("analysis_mode") == "hybrid" and len(result.get("discovered_tables") or {}) == 0:
                    pass
                else:
                    state_key = state_key_discovery(ddl_hash, use_db, desc_hash)
                    state_to_save = dict(result)
                    state_to_save["blocks"] = getattr(analyzer, "blocks", [])
                    state_to_save["view_to_tables_map"] = getattr(analyzer, "view_to_tables_map", {})
                    state_to_save["variables"] = getattr(analyzer, "variables", {})
                    state_to_save["function_params"] = getattr(analyzer, "function_params", [])
                    state_to_save["function"] = getattr(analyzer, "func_name", "unknown")
                    state_to_save["temp_tables"] = list(getattr(analyzer, "temp_tables", []))
                    state_to_save["physical_tables"] = [list(p) for p in getattr(analyzer, "physical_tables", set())]
                    set_state(state_key, state_to_save)
            except Exception:
                pass

    except Exception as e:
        err_safe = _mask_secret(str(e))
        _analysis_orchestrator.fail_job(job_id, err_safe)
        _enqueue_log(job_id, f"\n❌ Ошибка: {err_safe}\n")
        log_event(
            "job.discovery.failed",
            request_id=payload.get("request_id"),
            job_id=job_id,
            stack=payload.get("stack"),
            error=err_safe,
        )
    finally:
        _enqueue_log(job_id, "\n[STREAM_END]\n")


def _run_analysis_job(job_id: str, payload: Dict[str, Any]) -> None:
    """Запуск второго этапа: анализ с пользовательскими размерами."""
    _ensure_event_loop()
    try:
        from llm.tracker import tracker_reset
        tracker_reset()
    except Exception:
        pass
    buf = _stream_stdout_to_queue(job_id)
    job: Optional[Dict[str, Any]] = None
    try:
        with redirect_stdout(buf):
            job = _analysis_orchestrator.require_job(job_id)
            log_event(
                "job.analysis.worker_started",
                request_id=job.get("request_id"),
                job_id=job_id,
                stack=job.get("stack"),
            )
            context = build_analysis_runtime_context(
                job,
                credentials_resolver=_agent_credentials,
                scope_resolver=_agent_scope,
            )
            analysis_mode = context.analysis_mode
            plan_source = context.plan_source
            use_db = context.use_db
            stack = context.stack
            runtime_descriptor = context.runtime_descriptor
            analyzer = context.analyzer
            agent_credentials = context.agent_credentials
            agent_scope = context.agent_scope
            log_runtime_execution_banner(
                stack_label=runtime_descriptor.ui.get("stack_label", stack),
                analysis_mode=analysis_mode,
                plan_source=plan_source,
                use_db=use_db,
                phase="analysis",
                agent_chat_model=_agent_chat_model_from(job),
                agent_embedding_model=_agent_embedding_model_from(job),
            )

            params = payload.get("params", [])
            if not params and "saved_params" in job:
                params = job["saved_params"]
                print(f"🔄 Использованы сохраненные параметры из saved_params: {params}")
            elif not params and "discovery_result" in job:
                params = job["discovery_result"].get("user_params", [])
                print(f"🔄 Использованы параметры из discovery: {params}")

            user_sizes = payload.get("user_sizes", {})
            print(f"🔍 Запуск анализа с параметрами: {params}")
            print(f"📊 Размеры таблиц: {len(user_sizes)} шт.")

            result = analyzer.analyze_with_user_sizes(
                params,
                user_sizes,
                analysis_mode=analysis_mode,
                plan_source=plan_source,
                agent_credentials=agent_credentials,
                agent_scope=agent_scope,
                agent_chat_model=_agent_chat_model_from(job),
                agent_embedding_model=_agent_embedding_model_from(job),
                agent_provider=_agent_provider_from(job),
                agent_stack=_agent_stack_from(job),
                agent_multi_agent=_agent_multi_agent_from(job),
            )
            result = _apply_runtime_quality_metadata(
                result, stack=stack, runtime_descriptor=runtime_descriptor, payload=job
            )
            result["stack"] = stack
            result["runtime_label"] = runtime_descriptor.ui.get("stack_label", stack)
            if isinstance(result, dict):
                result["agent_chat_model"] = _agent_chat_model_from(job)
                result["agent_embedding_model"] = _agent_embedding_model_from(job)
                result["agent_provider"] = _agent_provider_from(job)
            _analysis_orchestrator.complete_analysis(job_id, result)
            log_event(
                "job.analysis.completed",
                request_id=job.get("request_id"),
                job_id=job_id,
                stack=stack,
                risk=result.get("risk"),
                analyzed_blocks=result.get("analyzed_blocks"),
            )
    except Exception as e:
        err_safe = _mask_secret(str(e))
        _analysis_orchestrator.fail_job(job_id, err_safe)
        _enqueue_log(job_id, f"\n❌ Ошибка: {err_safe}\n")
        log_event(
            "job.analysis.failed",
            request_id=(job or {}).get("request_id") if isinstance(job, dict) else payload.get("request_id"),
            job_id=job_id,
            error=err_safe,
        )
        traceback.print_exc()
    finally:
        _enqueue_log(job_id, "\n[STREAM_END]\n")
