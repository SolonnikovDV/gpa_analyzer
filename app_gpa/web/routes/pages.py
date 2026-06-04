"""Home / static page routes."""
from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("pages", __name__)


@bp.route("/")
def home_index():
    """Титульная страница — обзор и быстрый старт."""
    return render_template("home.html")


@bp.route("/about")
def about_page():
    """Отдельная страница «О приложении»."""
    return render_template("about.html")
