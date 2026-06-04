#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flask application entry point.

All routes are registered via blueprints in web/routes/.
All shared state lives in web/context.py.
All lifecycle hooks live in web/hooks.py.
The Flask app is created by web/factory.py::create_flask_app().

To start the server:
    python app_gpa/webapp.py
"""
from core.bootstrap import startup
from core.compat import install_compat_imports
from core.paths import ensure_runtime_dirs

install_compat_imports()
ensure_runtime_dirs()
startup()

from core.settings import settings
from web.factory import create_flask_app

app = create_flask_app()

# Legacy test compatibility layer ------------------------------------------------
# A number of integration tests monkeypatch module-level state on `webapp`.
# Keep these aliases so old fixtures can override runtime state without reaching
# into internal modules directly.
from web import context as _web_context  # noqa: E402
from web.routes import analysis as _analysis_routes  # noqa: E402

_preset_store = _web_context._preset_store
_job_service = _web_context._job_service
_performance_monitors = _web_context._performance_monitors
_analysis_orchestrator = _web_context._analysis_orchestrator
_persistence = _web_context._persistence


def _sync_legacy_state() -> None:
    _web_context._preset_store = _preset_store
    _web_context._job_service = _job_service
    _web_context._performance_monitors = _performance_monitors
    _web_context._analysis_orchestrator = _analysis_orchestrator
    _web_context._persistence = _persistence

    _analysis_routes._job_service = _job_service
    _analysis_routes._performance_monitors = _performance_monitors
    _analysis_routes._analysis_orchestrator = _analysis_orchestrator


@app.before_request
def _legacy_sync_before_request():
    _sync_legacy_state()


def _run_discovery_job(job_id, payload):
    _sync_legacy_state()
    return _analysis_routes._run_discovery_job(job_id, payload)


def _run_analysis_job(job_id, payload):
    _sync_legacy_state()
    return _analysis_routes._run_analysis_job(job_id, payload)

if __name__ == "__main__":
    app.run(host=settings.flask_host, port=settings.flask_port, debug=settings.flask_debug)
