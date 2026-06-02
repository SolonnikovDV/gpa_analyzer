# Functional Module Map

## Core Kernel

- `app_gpa/core/factory.py`: module registry and lifecycle orchestration.
- `app_gpa/core/bootstrap.py`: startup sequence and module wiring.
- `app_gpa/core/settings.py`, `app_gpa/core/paths.py`: runtime configuration and canonical paths.

## Analysis Domain

- `app_gpa/modules/analysis/*`: Greenplum/Spark/PySpark analyzers, SQL parsing, linting, runtime checks.
- `app_gpa/services/sql/*`, `app_gpa/services/runtime/*`: use-case layer for API adapters.

## Agent Domain

- `app_gpa/modules/agents/*`: providers, model clients, governance, orchestration, token and profile flow.
- `app_gpa/services/agents/api.py`: business API for generation, validation, profile operations.

## API Layer (Canonical)

- `app_gpa/api/app_factory.py`: FastAPI app creation and middleware wiring.
- `app_gpa/api/routers/*`: canonical `/api/*` endpoints (`agent`, `sql`, `runtime`, `cache`, `health`).

## Web Layer (Legacy/Transitional)

- `app_gpa/web/factory.py`, `app_gpa/web/routes/*`: Flask blueprints for HTML and compatibility paths.
- `app_gpa/webapp.py`: Flask entrypoint, used as fallback and mounted via WSGI in hybrid mode.

## Infrastructure and Runtime

- `app_gpa/infrastructure/*`: integration placeholders/adapters.
- `app_gpa/worker.py`: RQ worker runtime.
- `app_gpa/var/*`: runtime state, cache, local stores.

## Testing and Ops

- `app_gpa/tests/*`: unit/integration coverage, including hybrid FastAPI+Flask checks.
- `scripts/*`: TIG/DCI tooling and repo operational scripts.
