# Documentation Maintenance Rules

## Update Triggers

Update `project_doc` when any of the following changes:

- module wiring (`core/bootstrap.py`, `core/factory.py`)
- API route ownership or contracts (`api/routers/*`, `web/routes/*`)
- runtime topology (`main.py`, `webapp.py`, middleware/security flow)
- service/module boundaries (`services/*`, `modules/*`)

## Mandatory Workflow

1. Run TIG preflight:
   - `bash scripts/tig-context.sh "." "origin/main"`
2. Apply documentation updates in `project_doc`.
3. Run TIG postflight:
   - `bash scripts/tig-context.sh "." "origin/main" --delta-only`
4. Confirm:
   - links in `project_doc` are valid
   - Factory-first and FastAPI-first invariants are still reflected
   - Flask remnants backlog is updated if legacy footprint changed

## Minimal Review Checklist

- Architecture docs match current code paths.
- New modules/services are represented in module map.
- Any new Flask `/api/*` footprint is added as architectural debt.
- Evolution baseline note is refreshed for major structural changes.
