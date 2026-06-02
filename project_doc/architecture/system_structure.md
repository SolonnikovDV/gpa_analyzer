# GPA Analyzer — Application Structure (Factory Pattern)

Migrated from `app_gpa/STRUCTURE.md` and normalized as canonical architecture structure documentation.

---

## Entry Points

| File | Role |
|------|------|
| `app_gpa/main.py` | ASGI entry: FastAPI `/api/*` + Flask pages via WSGIMiddleware |
| `app_gpa/webapp.py` | Legacy Flask pages, HTML, SSE, long-running job routes |
| `app_gpa/worker.py` | RQ worker for background jobs |

```bash
cd app_gpa
python main.py                            # recommended (ASGI, all routes)
python webapp.py                          # Flask-only fallback
python scripts/check_agent_track.py      # agent smoke test
```

---

## Layer Map

```text
app_gpa/
├── core/                   ← Application kernel (no domain logic)
│   ├── factory.py          ← AppFactory: module registry + wire()
│   ├── settings.py         ← AppSettings (pydantic-settings)
│   ├── paths.py            ← Canonical FS paths: APP_DIR, CONFIG_DIR, VAR_DIR, …
│   ├── bootstrap.py        ← Startup: restore baseline + register_modules()
│   └── compat.py           ← agent.* → modules.agents.* transparent shim
│
├── config/                 ← Committed JSON configs
│   ├── agent_profiles.json
│   └── sql_function_profiles.json
│
├── var/                    ← Runtime state (gitignored)
│   └── agent_cache/        ← SQLite / JSON agent cache
│
├── modules/                ← Domain plug-in modules
│   ├── agents/             ← LLM agent module
│   │   ├── models/         ← Stack executors (gigachat, deepseek, groq, openrouter)
│   │   ├── providers/      ← Provider adapters implementing AgentProvider Protocol
│   │   ├── flow/           ← UI flow factory and handlers
│   │   ├── governance/     ← Roles, manifest, policy, prompt composition
│   │   └── orchestrator.py
│   └── analysis/           ← SQL/Spark/PySpark analysis module
│       ├── models/         ← Stack-specific executors (greenplum, spark, pyspark)
│       ├── lint/           ← Linter factory + stack linters
│       ├── detailed_analyzer.py
│       ├── runtime_analyzers.py
│       ├── analysis_orchestrator.py
│       ├── job_*.py
│       └── persistence and registry helpers
│
├── services/               ← Use-cases (no HTTP knowledge)
│   ├── agents/api.py
│   ├── sql/lint_service.py
│   ├── runtime/service.py
│   └── cache/service.py
│
├── api/                    ← FastAPI routers → services
│   ├── app_factory.py
│   ├── contracts.py
│   └── routers/ (agent/sql/runtime/cache/health)
│
├── web/                    ← Flask factory + blueprints + templates
│   ├── factory.py
│   ├── routes/
│   └── templates/ (+ static/)
│
├── scripts/                ← CLI / admin scripts
├── tests/                  ← pytest
├── infrastructure/         ← placeholder adapters
├── main.py
├── webapp.py
├── worker.py
└── requirements.txt
```

---

## Factory Wiring

```python
# app_gpa/core/bootstrap.py
from core.factory import AppFactory
from modules.agents import AgentModule
from modules.analysis import AnalysisModule

AppFactory.register("agents", AgentModule())
AppFactory.register("analysis", AnalysisModule())
AppFactory.wire()
```

`ModuleBase` protocol (`app_gpa/core/factory.py`):

| Method | Purpose |
|--------|---------|
| `setup()` | One-time init: dirs, DB tables, warm-up |
| `health()` | Status dict for `/api/health` aggregation |
| `metadata()` | Capabilities, version, config summary |

---

## HTTP → LLM Flow

```text
HTTP Request
  ├─ FastAPI /api/*  ──▶ services/agents/api.py
  │                              │
  │                         AgentModule
  │                              │
  │                        orchestrator.py
  │                              │
  │                     providers/registry.py
  │                       ┌──────┴──────┐
  │                 GigaChatProvider  DeepSeekProvider
  │
  └─ Flask /api/agent/generate  ──▶ transitional proxy path (legacy)
```

---

## Data Paths

| Path | Content |
|------|---------|
| `app_gpa/config/agent_profiles.json` | Saved LLM connection profiles |
| `app_gpa/config/sql_function_profiles.json` | SQL function runtime profiles |
| `app_gpa/var/agent_cache/` | Agent SQLite cache (gitignored) |
| `app_gpa/var/jobs.db` | Job store SQLite (gitignored) |

---

## Import Compatibility

`app_gpa/core/compat.py` redirects legacy imports:

```python
import agent.credentials          # -> modules.agents.credentials
import detailed.detailed_analyzer # -> modules.analysis.detailed_analyzer
```

Direct `from modules.*` imports are preferred in new code.  
Compat layer is removable after full import migration.
