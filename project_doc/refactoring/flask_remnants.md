# Flask Remnants Backlog

This register tracks Flask artifacts that conflict with the FastAPI-first target.

## Classification Rules

- `critical`: duplicates canonical `/api/*` behavior or blocks migration.
- `major`: strong coupling to Flask runtime that increases migration cost.
- `minor`: compatibility/helper footprint that can be removed after primary migration.

## Debt Register

| Area | Current Artifact | Why Legacy | FastAPI Target | Priority | Risks | Exit Criteria |
|------|------------------|------------|----------------|----------|-------|---------------|
| API duplication | `app_gpa/web/routes/agent.py` (`/api/agent/*`) | Flask JSON routes overlap canonical API responsibility | Keep only FastAPI `app_gpa/api/routers/agent.py`; remove Flask JSON endpoints | critical | UI paths may still call Flask routes directly | No Flask `/api/agent/*` endpoints registered in any mode |
| API duplication | `app_gpa/web/routes/sql.py` (`/api/sql/*`) | Duplicated contract surface | FastAPI `app_gpa/api/routers/sql.py` only | critical | Clients may rely on old fallback mode | Flask SQL API removed, tests pass on FastAPI endpoints |
| API duplication | `app_gpa/web/routes/runtime.py` (`/api/runtime*`) | Transitional duplicate runtime APIs | FastAPI `app_gpa/api/routers/runtime.py` | critical | Preset/test actions might depend on Flask context | Runtime API served only via FastAPI |
| API duplication | `app_gpa/web/routes/cache.py` (`/api/cache/*`) | Duplicated operational API | FastAPI `app_gpa/api/routers/cache.py` | major | Cache admin scripts may hit legacy endpoints | Cache API removed from Flask and covered by FastAPI tests |
| API duplication | `app_gpa/web/routes/db.py` (`/api/db/test`) | Legacy API placement | Move to dedicated FastAPI router/service | major | DB test UI integration may break if not rewired | Endpoint available only in FastAPI layer |
| Hybrid mount | `app_gpa/main.py` + `WSGIMiddleware(webapp.app)` | Keeps Flask runtime in process as primary dependency | Reduce Flask scope to pure HTML or migrate to FastAPI-native UI serving | major | SSE/jobs/pages currently coupled to Flask globals | Flask mount no longer required for JSON/API behavior |
| Flask app kernel | `app_gpa/web/factory.py`, `app_gpa/web/hooks.py` | Security/auth/rate-limit logic duplicated between frameworks | Single policy layer aligned with FastAPI middleware and shared services | major | Divergent auth/headers behavior across layers | Parity checks pass and duplicate hook logic removed |
| Legacy contracts | `app_gpa/modules/analysis/api_contracts.py` (Flask Response) | Domain module imports web-framework symbols | Replace with framework-agnostic contracts in service layer | major | Breaks tests expecting Flask response types | Contracts become framework-neutral |
| Legacy entrypoint | `app_gpa/webapp.py` | Standalone Flask mode retains old architecture path | Keep temporary fallback only; plan removal after migration | minor | Dev workflow still uses Flask-only run mode | FastAPI mode is the only supported production path |

## Recommended Refactoring Stages

1. Eliminate Flask `/api/*` route ownership in all run modes.
2. Rewire UI calls to FastAPI endpoints.
3. Move framework-specific response helpers out of domain modules.
4. Reduce Flask usage to optional UI shell, then retire if feasible.
