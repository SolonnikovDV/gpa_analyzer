# GPA Analyzer — Application Structure (Factory Pattern)

> Single source of truth for the project layout.  
> Inline docs in `ARCHITECTURE.md` or `ORCHESTRATION_PLAN.md` inside sub-packages have been removed.

---

## Entry Points

| File | Role |
|------|------|
| `main.py` | ASGI entry: FastAPI `/api/*` + Flask pages via WSGIMiddleware |
| `webapp.py` | Legacy Flask pages, HTML, SSE, long-running job routes |
| `worker.py` | RQ worker for background jobs |

```bash
cd app_gpa
python main.py                            # recommended (ASGI, all routes)
python webapp.py                          # Flask-only fallback
python scripts/check_agent_track.py      # agent smoke test
```

---

## Layer Map

```
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
│   │                         Each has a public __init__.py (ModuleBase)
│   ├── agents/             ← LLM agent module
│   │   ├── __init__.py     ← AgentModule (setup / health / metadata)
│   │   ├── models/         ← Stack executors (NEW)
│   │   │   ├── gigachat/   ← GigaChat SDK lifecycle (client.py) + actions (actions.py)
│   │   │   └── deepseek/   ← DeepSeek placeholder
│   │   ├── providers/      ← HTTP adapters implementing AgentProvider Protocol
│   │   │   ├── base.py
│   │   │   ├── gigachat_provider.py
│   │   │   ├── deepseek.py
│   │   │   └── registry.py
│   │   ├── orchestrator.py ← Provider selection + governance enrichment
│   │   ├── flow/           ← UI flow factory (profile handlers, plan builder)
│   │   ├── governance/     ← Roles, manifest, multi-agent policy, prompt composer
│   │   ├── gigachat_agent.py  ← Legacy monolith (being decomposed into models/)
│   │   ├── agent_cache_db.py
│   │   ├── agent_prompts.py
│   │   ├── credentials.py
│   │   ├── embedding_policy.py
│   │   ├── token_usage.py
│   │   └── track.py
│   │
│   └── analysis/           ← SQL/Spark analysis module
│       ├── __init__.py     ← AnalysisModule (setup / health / metadata)
│       ├── models/         ← Stack-specific executors (NEW)
│       │   ├── greenplum/  ← GreenplumAnalyzer
│       │   ├── spark/      ← SparkAnalyzer
│       │   └── pyspark/    ← PySparkAnalyzer
│       ├── lint/           ← Linter factory + stack linters
│       ├── detailed_analyzer.py  ← GreenPlum function analysis engine
│       ├── runtime_analyzers.py  ← Spark / PySpark runtime analyzers
│       ├── analysis_orchestrator.py
│       ├── job_*.py        ← Job contracts, store, runner, service
│       ├── persistence_service.py
│       ├── runtime_registry.py
│       ├── runtime_preset_store.py
│       └── …
│
├── services/               ← Use-cases (no HTTP knowledge)
│   ├── agents/api.py       ← Agent business logic (credentials, flow, token)
│   ├── sql/lint_service.py ← SQL validation use-cases
│   ├── runtime/service.py  ← Runtime descriptor + stand tests
│   └── cache/service.py    ← Agent cache management
│
├── api/                    ← FastAPI routers → services
│   ├── app_factory.py      ← create_fastapi_app()
│   ├── contracts.py        ← ok_payload / error_payload helpers
│   └── routers/
│       ├── agent.py        ← /api/agent/* (incl. POST /generate)
│       ├── sql.py          ← /api/sql/*
│       ├── runtime.py      ← /api/runtime/*
│       ├── cache.py        ← /api/cache/*
│       └── health.py       ← /api/health
│
├── web/                    ← Flask factory + blueprints + templates
│   ├── factory.py
│   ├── routes/
│   └── templates/ (+ static/)
│
├── scripts/                ← CLI / admin scripts
│   ├── check_gigachat_connection.py
│   ├── check_deepseek_connection.py
│   ├── check_agent_track.py
│   └── validate_gigachat_models.py
│
├── tests/                  ← pytest
├── infrastructure/         ← (placeholder) DB adapters, Redis clients
├── main.py
├── webapp.py
├── worker.py
└── requirements.txt
```

---

## Factory Wiring

```python
# core/bootstrap.py
from core.factory import AppFactory
from modules.agents import AgentModule
from modules.analysis import AnalysisModule

AppFactory.register("agents", AgentModule())
AppFactory.register("analysis", AnalysisModule())
AppFactory.wire()          # calls setup() on each module
```

`ModuleBase` Protocol (in `core/factory.py`):

| Method | Purpose |
|--------|---------|
| `setup()` | One-time init: dirs, DB tables, warm-up |
| `health()` | Status dict for `/api/health` aggregation |
| `metadata()` | Capabilities, version, config summary |

---

## Adding a New Agent (e.g. YandexGPT)

1. `modules/agents/models/yandexgpt/__init__.py` — client + actions
2. `modules/agents/providers/yandexgpt_provider.py` — `AgentProvider` impl
3. One line in `modules/agents/providers/registry.py` — add to `_PROVIDERS`

**No other files change.**

---

## HTTP → LLM Flow

```
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
  │                    models/gigachat/  models/deepseek/
  │
  └─ Flask /api/agent/generate  ──▶ same service path (proxy)
```

---

## Data Paths

| Path | Content |
|------|---------|
| `config/agent_profiles.json` | Saved LLM connection profiles |
| `config/sql_function_profiles.json` | SQL function runtime profiles |
| `var/agent_cache/` | Agent SQLite cache (gitignored) |
| `var/jobs.db` | Job store SQLite (gitignored) |

---

## Import Compatibility

`core/compat.py` transparently redirects legacy imports:

```python
import agent.credentials          # → modules.agents.credentials
import detailed.detailed_analyzer # → modules.analysis.detailed_analyzer
```

Direct `from modules.*` imports are preferred in all new code.  
The compat layer can be removed once all callers are migrated.
