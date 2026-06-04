"""System pages: license and health-adjacent routes."""
from __future__ import annotations

import os

from flask import Blueprint, send_file

from core.paths import PROJECT_ROOT

bp = Blueprint("system", __name__)


@bp.route("/license")
def license_page():
    path = PROJECT_ROOT / "LICENSE"
    if not path.is_file():
        return "License file not found", 404
    return send_file(path, mimetype="text/plain", as_attachment=False, download_name="LICENSE")
