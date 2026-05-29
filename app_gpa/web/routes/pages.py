"""Home / static page routes."""
from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("pages", __name__)


@bp.route("/")
def home_index():
    """Титульная страница — обзор и быстрый старт."""
    return render_template("home.html")
