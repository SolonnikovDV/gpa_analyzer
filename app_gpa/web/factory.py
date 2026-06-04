"""Flask application factory (HTML pages, legacy routes)."""
from __future__ import annotations

import os
from datetime import datetime

from flask import Flask
from jinja2 import ChoiceLoader, FileSystemLoader

from core.paths import WEB_STATIC_DIR, WEB_TEMPLATE_DIRS
from core.settings import settings


def create_flask_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(WEB_STATIC_DIR),
        static_url_path="/static",
    )
    app.secret_key = settings.secret_key
    app.config["MAX_CONTENT_LENGTH"] = settings.max_content_length_bytes
    app.config["SESSION_COOKIE_HTTPONLY"] = settings.session_cookie_httponly
    app.config["SESSION_COOKIE_SECURE"] = settings.session_cookie_secure
    app.config["SESSION_COOKIE_SAMESITE"] = settings.session_cookie_samesite
    app.config["PERMANENT_SESSION_LIFETIME"] = settings.session_lifetime

    if not settings.flask_debug and settings.uses_default_secret_key:
        raise RuntimeError("APP_SECRET_KEY must be set for non-debug mode.")
    if settings.basic_auth_username and not settings.basic_auth_password:
        raise RuntimeError("APP_BASIC_AUTH_PASSWORD must be set when APP_BASIC_AUTH_USERNAME is configured.")
    if settings.basic_auth_password and not settings.basic_auth_username:
        raise RuntimeError("APP_BASIC_AUTH_USERNAME must be set when APP_BASIC_AUTH_PASSWORD is configured.")

    app.jinja_loader = ChoiceLoader([FileSystemLoader(str(path)) for path in WEB_TEMPLATE_DIRS])

    from web.routes.register import register_blueprints
    from web.hooks import register_hooks

    register_blueprints(app)
    register_hooks(app)

    @app.context_processor
    def inject_app_info():
        return {
            "app_name": settings.app_name,
            "app_author": settings.app_author,
            "app_version": settings.app_version,
            "app_description": settings.app_description,
            "app_year": datetime.now().year,
        }

    return app
