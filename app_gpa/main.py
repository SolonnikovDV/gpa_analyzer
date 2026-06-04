#!/usr/bin/env python3
"""Primary ASGI entry point — FastAPI /api/* + Flask HTML/jobs/SSE.

Run with:
    uvicorn app_gpa.main:app --host 0.0.0.0 --port 8080
or:
    python app_gpa/main.py
"""
from __future__ import annotations

import os

# Signal to Flask blueprint registration that JSON /api/* routes are owned by
# FastAPI — Flask should NOT register duplicate API blueprints in this mode.
os.environ["GPA_HYBRID_MODE"] = "1"

from core.bootstrap import restore_agent_baseline
from core.compat import install_compat_imports
from core.paths import ensure_runtime_dirs

install_compat_imports()
ensure_runtime_dirs()
restore_agent_baseline()

from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware

from api.app_factory import create_api_app


def create_app() -> FastAPI:
    root = FastAPI(title="GPA Analyzer", docs_url="/api/docs", openapi_url="/api/openapi.json")
    api = create_api_app()
    root.mount("/api", api)

    import webapp

    root.mount("/", WSGIMiddleware(webapp.app))
    return root


app = create_app()


if __name__ == "__main__":
    import uvicorn

    from core.settings import settings

    host = getattr(settings, "uvicorn_host", settings.flask_host)
    port = getattr(settings, "uvicorn_port", settings.flask_port)
    uvicorn.run("main:app", host=host, port=port, reload=settings.flask_debug)
