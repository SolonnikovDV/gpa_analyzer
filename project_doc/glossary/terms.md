# Glossary

- **Factory-first**: application modules are explicitly registered and wired through `AppFactory`, not by implicit side effects.
- **FastAPI-first**: JSON API ownership is centralized in FastAPI routers under `app_gpa/api/routers/*`.
- **Flask remnant**: any Flask runtime artifact that still owns API behavior intended for FastAPI.
- **Hybrid mode**: runtime topology where FastAPI mounts Flask through `WSGIMiddleware`.
- **ModuleBase**: required module protocol (`setup`, `health`, `metadata`) used by `AppFactory`.
- **Canonical documentation**: architecture/structure docs stored under `project_doc`.
- **infrastructure_non_movable**: documentation artifact intentionally left at source path to preserve repository/process contracts.
