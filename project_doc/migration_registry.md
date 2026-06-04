# Documentation Migration Registry

Policy: full move without stubs by default.  
Exception: if move can break infrastructure/process expectations, keep in place and mark `infrastructure_non_movable`.

## Migration Decisions

| Source | Decision | Target | Status | Notes |
|--------|----------|--------|--------|-------|
| `app_gpa/STRUCTURE.md` | moved | `project_doc/architecture/system_structure.md` | completed | Canonical architecture structure moved to unified docs |
| `README.md` | infrastructure_non_movable | `project_doc/index.md` (linked) | retained | Repo entrypoint must remain at root for discoverability/tooling |
| `gpa_project_struct.md` | infrastructure_non_movable | `project_doc/evolution/tig_baseline_2026-06-01.md` (summarized) | retained | Historical/generated heavy TIG snapshot archive; kept as raw artifact |

## Follow-up Rule

For future migrations, update this registry in the same commit as document changes.
