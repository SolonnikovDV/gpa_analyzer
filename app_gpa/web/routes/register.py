"""Register Flask blueprints on the Flask application.

Blueprint scope (hybrid main.py mode):
  pages    — HTML page renders (/, /analyze, /about, etc.)
  analysis — SSE streams (/stream/*) and async job management (/jobs/*)
  health   — /health/* (Flask-side; FastAPI has its own /api/health/*)
  system   — admin/system utilities
  agent    — HTML-adjacent agent routes ONLY (form submissions, redirects)
             NOTE: All JSON /api/agent/* endpoints are now in FastAPI
                   (api/routers/agent.py). The Flask agent blueprint must NOT
                   register duplicate /api/agent/* JSON routes when running
                   under main.py (FastAPI) — those are handled by FastAPI first.

Blueprints NOT registered in main.py hybrid mode:
  sql, runtime, cache, db  — their /api/* routes live in FastAPI routers.
"""
from __future__ import annotations

import os

from flask import Flask

# Set by main.py before Flask app creation so Flask blueprint registration
# can detect which mode it is running in.
_HYBRID_MODE: bool = os.environ.get("GPA_HYBRID_MODE", "0") == "1"


def register_blueprints(app: Flask) -> None:
    from web.routes.health import bp as health_bp
    from web.routes.pages import bp as pages_bp
    from web.routes.analysis import bp as analysis_bp
    from web.routes.system import bp as system_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(system_bp)

    if not _HYBRID_MODE:
        # In standalone Flask mode (webapp.py), register all API blueprints so
        # the app works without FastAPI in front.
        from web.routes.agent import bp as agent_bp
        from web.routes.sql import bp as sql_bp
        from web.routes.runtime import bp as runtime_bp
        from web.routes.cache import bp as cache_bp
        from web.routes.db import bp as db_bp

        app.register_blueprint(agent_bp)
        app.register_blueprint(sql_bp)
        app.register_blueprint(runtime_bp)
        app.register_blueprint(cache_bp)
        app.register_blueprint(db_bp)
