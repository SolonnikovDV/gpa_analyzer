from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta


WEBAPP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(WEBAPP_DIR)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip()
    return normalized or default


def load_project_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    for candidate_dir in (PROJECT_ROOT, WEBAPP_DIR):
        env_path = os.path.join(candidate_dir, ".env")
        if os.path.isfile(env_path):
            load_dotenv(env_path)
            return
    load_dotenv()


@dataclass(frozen=True)
class AppSettings:
    secret_key: str
    flask_host: str
    flask_port: int
    flask_debug: bool
    job_runner_backend: str
    redis_url: str
    job_queue_name: str
    max_content_length_bytes: int
    basic_auth_username: str
    basic_auth_password: str
    rate_limit_enabled: bool
    rate_limit_requests: int
    rate_limit_window_seconds: int
    session_cookie_secure: bool
    session_cookie_httponly: bool
    session_cookie_samesite: str
    session_lifetime_minutes: int
    app_name: str
    app_author: str
    app_version: str
    app_description: str
    runtime_store_dir: str
    persistence_db_path: str

    @classmethod
    def from_env(cls) -> "AppSettings":
        return cls(
            secret_key=os.environ.get("APP_SECRET_KEY", "your-secret-key-here-change-this-in-production"),
            flask_host=os.environ.get("FLASK_HOST", "0.0.0.0"),
            flask_port=_env_int("FLASK_PORT", 8003),
            flask_debug=_env_bool("FLASK_DEBUG", True),
            job_runner_backend=os.environ.get("JOB_RUNNER_BACKEND", "thread").strip().lower() or "thread",
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0").strip() or "redis://localhost:6379/0",
            job_queue_name=os.environ.get("JOB_QUEUE_NAME", "gpa-jobs").strip() or "gpa-jobs",
            max_content_length_bytes=_env_int("MAX_CONTENT_LENGTH_BYTES", 2 * 1024 * 1024),
            basic_auth_username=_env_str("APP_BASIC_AUTH_USERNAME", ""),
            basic_auth_password=_env_str("APP_BASIC_AUTH_PASSWORD", ""),
            rate_limit_enabled=_env_bool("RATE_LIMIT_ENABLED", False),
            rate_limit_requests=_env_int("RATE_LIMIT_REQUESTS", 120),
            rate_limit_window_seconds=_env_int("RATE_LIMIT_WINDOW_SECONDS", 60),
            session_cookie_secure=_env_bool("SESSION_COOKIE_SECURE", False),
            session_cookie_httponly=_env_bool("SESSION_COOKIE_HTTPONLY", True),
            session_cookie_samesite=_env_str("SESSION_COOKIE_SAMESITE", "Lax"),
            session_lifetime_minutes=_env_int("SESSION_LIFETIME_MINUTES", 120),
            app_name=os.environ.get("APP_NAME", "GPA Analyzer"),
            app_author=os.environ.get("APP_AUTHOR", "Dmitry Solonnikov"),
            app_version=os.environ.get("APP_VERSION", "1.0"),
            app_description=os.environ.get(
                "APP_DESCRIPTION",
                "Оценка нагрузки и рисков выполнения PL/pgSQL-функций в Greenplum по планам запросов.",
            ),
            runtime_store_dir=os.environ.get("RUNTIME_STORE_DIR", os.path.join(PROJECT_ROOT, ".runtime_store")),
            persistence_db_path=os.environ.get(
                "PERSISTENCE_DB_PATH",
                os.path.join(
                    os.environ.get("RUNTIME_STORE_DIR", os.path.join(PROJECT_ROOT, ".runtime_store")),
                    "app_state.sqlite3",
                ),
            ),
        )

    @property
    def session_lifetime(self) -> timedelta:
        return timedelta(minutes=max(1, self.session_lifetime_minutes))

    # Placeholders that must be replaced before production (incl. Docker default)
    _INSECURE_SECRET_PLACEHOLDERS = (
        "your-secret-key-here-change-this-in-production",
        "change-me-before-production",
    )

    @property
    def uses_default_secret_key(self) -> bool:
        return (self.secret_key or "").strip() in self._INSECURE_SECRET_PLACEHOLDERS

    @property
    def basic_auth_enabled(self) -> bool:
        return bool(self.basic_auth_username and self.basic_auth_password)


load_project_environment()
settings = AppSettings.from_env()
