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

if __name__ == "__main__":
    app.run(host=settings.flask_host, port=settings.flask_port, debug=settings.flask_debug)
