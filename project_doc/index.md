# GPA Project Documentation Index

`project_doc` is the canonical architecture and structure documentation for GPA Analyzer.

## Read Order

1. [Architecture Principles](architecture/architecture_principles.md)
2. [System Structure](architecture/system_structure.md)
3. [Module Map](modules/module_map.md)
4. [Flask Remnants Backlog](refactoring/flask_remnants.md)
5. [TIG Baseline](evolution/tig_baseline_2026-06-01.md)
6. [Maintenance Rules](maintenance.md)
7. [Migration Registry](migration_registry.md)
8. [Glossary](glossary/terms.md)
9. [UX Audit Log](ux/ux_audit_log.md)
10. [UX Focus Group Round 1](ux/focus_group_round1.md)
11. [UX Focus Group Round 2](ux/focus_group_round2.md)
12. [UX Design Consistency Checklist](ux/design_consistency_checklist.md)
13. [UX Final Consensus Report](ux/final_consensus_report.md)

## Scope

- Factory-first architecture (`core/factory.py` + module lifecycle).
- FastAPI-first JSON API (`app_gpa/api/routers/*`).
- Legacy Flask surface tracked as explicit architectural debt.
- Structural and evolution context aligned to TIG artifacts.

## Source Policy

- Canonical source for architecture/structure lives in `project_doc`.
- Repo-level `README.md` remains a product entrypoint and links here.
- Historical heavy snapshots remain outside canonical docs when marked `infrastructure_non_movable`.
