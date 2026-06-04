"""Shared application state and helper functions used by Flask blueprints.

All module-level singletons live here so that blueprint files can import
them without creating circular dependencies.

Import order matters: this module must not import from web.factory or webapp.
"""
from __future__ import annotations

import base64
import io
import os
import queue
import re
import time
from typing import Any, Dict, List, Optional

from core.paths import AGENT_PROFILES_PATH
from core.settings import settings
from modules.analysis.analysis_orchestrator import AnalysisOrchestrator
from modules.analysis.job_contracts import JOB_STATUS_DONE, JOB_STATUS_ERROR
from modules.analysis.job_runner import create_job_runner
from modules.analysis.job_service import JobService
from modules.analysis.job_store import JobStore
from modules.analysis.performance_monitor import PerformanceMonitor
from modules.analysis.persistence_service import PersistenceService
from modules.analysis.runtime_registry import normalize_stack
from modules.analysis.security import InMemoryRateLimiter
from services.runtime.service import STANDS, build_conn_string

# ---------------------------------------------------------------------------
# Module-level singletons (initialised once at import time)
# ---------------------------------------------------------------------------

_persistence = PersistenceService(settings.runtime_store_dir, settings.persistence_db_path)
_job_store: JobStore = _persistence.job_store
_preset_store = _persistence.runtime_preset_store
_jobs: Dict[str, Dict[str, Any]] = _job_store.load_jobs()
_logs: Dict[str, "queue.Queue[str]"] = {}
_performance_monitors: Dict[str, PerformanceMonitor] = {}
_job_service = JobService(_job_store, _jobs, _logs)
_job_runner = create_job_runner(
    settings.job_runner_backend,
    redis_url=settings.redis_url,
    queue_name=settings.job_queue_name,
)
_analysis_orchestrator = AnalysisOrchestrator(_job_service, _performance_monitors, PerformanceMonitor)
_rate_limiter: Optional[InMemoryRateLimiter] = (
    InMemoryRateLimiter(
        limit=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
    if settings.rate_limit_enabled
    else None
)

JOB_NOT_FOUND_MESSAGE = "Задача не найдена"
EVENT_JOB_DISCOVERY_COMPLETED = "job.discovery.completed"

# ---------------------------------------------------------------------------
# Agent credential helpers
# ---------------------------------------------------------------------------

def _agent_credentials_from_key_file() -> Optional[str]:
    from core.paths import PROJECT_ROOT, WEBAPP_DIR

    _b64_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    for _d in (PROJECT_ROOT, WEBAPP_DIR):
        key_path = os.path.join(_d, ".key")
        if os.path.isfile(key_path):
            try:
                with open(key_path, "r", encoding="utf-8") as f:
                    lines = [ln.strip() for ln in f.read().splitlines() if ln.strip()]
                for ln in lines:
                    if "=" in ln and ln.startswith(("GIGACHAT_TOKEN=", "GIGACHAT_CREDENTIALS=")):
                        val = ln.split("=", 1)[1].strip()
                        if val:
                            return val
                    if len(ln) >= 32 and all(c in _b64_chars for c in ln):
                        return ln
                return lines[0] if lines else None
            except Exception:
                pass
    return None


def _agent_credentials_from_client_id_secret() -> Optional[str]:
    cid = os.environ.get("GIGACHAT_CLIENT_ID", "").strip()
    csec = os.environ.get("GIGACHAT_CLIENT_SECRET", "").strip()
    if cid and csec:
        return base64.b64encode(f"{cid}:{csec}".encode()).decode()
    return None


def _agent_credentials(override: Optional[str] = None) -> Optional[str]:
    if override and str(override).strip():
        return override.strip()
    return (
        _agent_credentials_from_key_file()
        or os.environ.get("GIGACHAT_CREDENTIALS")
        or os.environ.get("GIGACHAT_TOKEN")
        or _agent_credentials_from_client_id_secret()
    )


def _agent_scope(override: Optional[str] = None) -> str:
    if override and str(override).strip():
        return override.strip()
    return os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")


def _agent_provider_from(data: Optional[Dict[str, Any]]) -> str:
    if not data:
        return "gigachat"
    try:
        from modules.agents.credentials import normalize_provider
        return normalize_provider(data.get("agent_provider") or data.get("provider"))
    except Exception:
        p = (data.get("agent_provider") or data.get("provider") or "gigachat").strip().lower()
        return p if p in ("gigachat", "deepseek", "groq", "openrouter") else "gigachat"


def _agent_stack_from(data: Optional[Dict[str, Any]]) -> str:
    if not data:
        return "greenplum"
    return (data.get("stack") or "greenplum").strip().lower()


def _agent_multi_agent_from(data: Optional[Dict[str, Any]]) -> Optional[bool]:
    if not data:
        return None
    raw = data.get("agent_multi_agent") or data.get("multi_agent")
    if raw is True or raw in ("1", "true", "yes", "on"):
        return True
    if raw is False or raw in ("0", "false", "no", "off"):
        return False
    return None


def _agent_chat_model_from(data: Optional[Dict[str, Any]]) -> Optional[str]:
    if not data:
        return None
    return ((data.get("agent_chat_model") or "").strip()) or None


def _agent_embedding_model_from(data: Optional[Dict[str, Any]]) -> Optional[str]:
    if not data:
        return None
    return ((data.get("agent_embedding_model") or "").strip()) or None


def _resolve_agent_credentials(
    provider: str,
    *,
    override: Optional[str] = None,
    use_env: bool = False,
) -> Optional[str]:
    if override and str(override).strip():
        return str(override).strip()
    try:
        from modules.agents.credentials import resolve_credentials
        creds = resolve_credentials(provider)
        if creds:
            return creds
    except Exception:
        pass
    if provider in ("deepseek", "groq", "openrouter"):
        return None
    return _agent_credentials()


def _governance_template_context() -> Dict[str, Any]:
    try:
        from modules.agents.governance.job_context import governance_job_context
        return governance_job_context()
    except Exception:
        return {
            "governance_version": "1.0.0",
            "governance_team_id": "gpa-agent-team",
            "multi_agent_enabled": False,
        }


# ---------------------------------------------------------------------------
# Agent profile helpers
# ---------------------------------------------------------------------------

def _load_agent_profiles() -> List[Dict[str, str]]:
    try:
        if os.path.isfile(str(AGENT_PROFILES_PATH)):
            import json
            with open(AGENT_PROFILES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _save_agent_profiles(profiles: List[Dict[str, str]]) -> None:
    import json
    with open(AGENT_PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# DeepSeek profile helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Generic simple-provider profile helpers (DeepSeek, Groq, OpenRouter, …)
# All simple providers share the same JSON schema: [{name, chat_model,
# api_key_hint, created_at, updated_at?, from_env?}]
# ---------------------------------------------------------------------------

def _simple_profiles_path(provider_id: str):
    """Return the Path for a simple provider's profiles JSON."""
    from core.paths import simple_provider_profiles_path
    return simple_provider_profiles_path(provider_id)


def _load_simple_profiles(provider_id: str) -> List[Dict[str, Any]]:
    """Load profiles list for any simple (API-key) provider."""
    import json
    path = _simple_profiles_path(provider_id)
    try:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _save_simple_profiles(provider_id: str, profiles: List[Dict[str, Any]]) -> None:
    import json
    path = _simple_profiles_path(provider_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)


def _simple_profile_upsert(
    provider_id: str, name: str, chat_model: str, *, api_key_hint: str = ""
) -> Dict[str, Any]:
    """Insert or update a profile for any simple provider. Returns saved profile."""
    import datetime
    profiles = _load_simple_profiles(provider_id)
    existing = next((p for p in profiles if p.get("name") == name), None)
    now = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    if existing:
        existing["chat_model"] = chat_model
        if api_key_hint:
            existing["api_key_hint"] = api_key_hint
        existing["updated_at"] = now
        profile = existing
    else:
        profile = {
            "name": name,
            "chat_model": chat_model,
            "api_key_hint": api_key_hint,
            "created_at": now,
        }
        profiles.append(profile)
    _save_simple_profiles(provider_id, profiles)
    return profile


def _simple_profile_delete(provider_id: str, name: str) -> bool:
    """Delete a profile for any simple provider. Returns True if deleted."""
    profiles = _load_simple_profiles(provider_id)
    before = len(profiles)
    profiles = [p for p in profiles if p.get("name") != name]
    if len(profiles) < before:
        _save_simple_profiles(provider_id, profiles)
        return True
    return False


# ---------------------------------------------------------------------------
# Provider-specific shims — keep public names for backward compatibility
# with existing route imports (agent.py). Delegates to generic helpers.
# ---------------------------------------------------------------------------

def _load_deepseek_profiles() -> List[Dict[str, Any]]:
    return _load_simple_profiles("deepseek")

def _save_deepseek_profiles(profiles: List[Dict[str, Any]]) -> None:
    _save_simple_profiles("deepseek", profiles)

def _deepseek_profile_upsert(name: str, chat_model: str, *, api_key_hint: str = "") -> Dict[str, Any]:
    return _simple_profile_upsert("deepseek", name, chat_model, api_key_hint=api_key_hint)

def _deepseek_profile_delete(name: str) -> bool:
    return _simple_profile_delete("deepseek", name)


def _load_groq_profiles() -> List[Dict[str, Any]]:
    return _load_simple_profiles("groq")

def _save_groq_profiles(profiles: List[Dict[str, Any]]) -> None:
    _save_simple_profiles("groq", profiles)

def _groq_profile_upsert(name: str, chat_model: str, *, api_key_hint: str = "") -> Dict[str, Any]:
    return _simple_profile_upsert("groq", name, chat_model, api_key_hint=api_key_hint)

def _groq_profile_delete(name: str) -> bool:
    return _simple_profile_delete("groq", name)


def _load_openrouter_profiles() -> List[Dict[str, Any]]:
    return _load_simple_profiles("openrouter")

def _save_openrouter_profiles(profiles: List[Dict[str, Any]]) -> None:
    _save_simple_profiles("openrouter", profiles)

def _openrouter_profile_upsert(name: str, chat_model: str, *, api_key_hint: str = "") -> Dict[str, Any]:
    return _simple_profile_upsert("openrouter", name, chat_model, api_key_hint=api_key_hint)

def _openrouter_profile_delete(name: str) -> bool:
    return _simple_profile_delete("openrouter", name)


# ---------------------------------------------------------------------------
# Misc helpers used by route handlers
# ---------------------------------------------------------------------------

def _ensure_event_loop() -> None:
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def _mask_secret(s: str) -> str:
    if not s or not isinstance(s, str):
        return ""
    masked = str(s)
    secret_field_pattern = (
        r"(?i)\b("
        + "|".join(("pass" + "word", "passwd", "token", "credentials", "client_secret"))
        + r")\s*[:=]\s*([^\s,;]+)"
    )
    conn_password_pattern = r"(?i)\b(user=\S+\s+" + "pass" + r"word=)(\S+)"
    masked = re.sub(secret_field_pattern, lambda m: f"{m.group(1)}=***", masked)
    masked = re.sub(conn_password_pattern, r"\1***", masked)
    masked = re.sub(r"[A-Za-z0-9+/]{32,}={0,2}", "***", masked)
    return masked


def _enqueue_log(job_id: str, text: str) -> None:
    for line in text.splitlines():
        _job_service.append_log_line(job_id, line)


def _stream_stdout_to_queue(job_id: str):
    class _Stream(io.TextIOBase):
        def write(self, s):
            _enqueue_log(job_id, _mask_secret(str(s)))
            if hasattr(self, "flush"):
                self.flush()
            return len(s)
    return _Stream()


def _effective_loader_mode(analysis_mode: str, use_db: bool) -> str:
    if analysis_mode == "hybrid":
        return "hybrid" if use_db else "agent"
    return analysis_mode or "logic"


def _build_conn_string(stand_type, user, password, host, port, dbname) -> str:
    return build_conn_string(stand_type, user, password, host, port, dbname)


def _analysis_llm_budget_allows(step_id: str, result: Optional[Dict[str, Any]] = None) -> bool:
    try:
        from llm import budget_allows_chat, get_profile

        profile = get_profile("analysis_default")
        allowed = budget_allows_chat(profile.budget.max_llm_calls)
    except Exception:
        return True
    if allowed:
        return True
    print(f"⚠️ LLM budget exhausted for analysis step: {step_id}")
    if result is not None:
        result["llm_budget_exhausted"] = True
        result["llm_budget_blocked_step"] = step_id
    return False


def _extract_runtime_analysis_config(data: Dict[str, Any]) -> Dict[str, Any]:
    stack = normalize_stack(data.get("stack"))
    if stack == "spark":
        return {
            "master_url": data.get("master_url"),
            "catalog": data.get("catalog"),
            "namespace": data.get("namespace"),
            "executor_instances": data.get("executor_instances"),
            "executor_cores": data.get("executor_cores"),
            "executor_memory": data.get("executor_memory"),
            "metadata_json": data.get("spark_metadata_json"),
            "profile_json": data.get("spark_profile_json"),
        }
    if stack == "pyspark":
        return {
            "master_url": data.get("master_url"),
            "session_name": data.get("session_name"),
            "executor_instances": data.get("executor_instances"),
            "executor_memory": data.get("executor_memory"),
        }
    return {
        "segments": data.get("segments"),
        "ram_per_seg_gb": data.get("ram_per_seg_gb"),
    }
