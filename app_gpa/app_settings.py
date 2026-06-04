"""Legacy settings entrypoint — use core.settings in new code."""
from core.compat import install_compat_imports

install_compat_imports()

from core.paths import APP_DIR, PROJECT_ROOT, WEBAPP_DIR  # noqa: F401
from core.settings import AppSettings, load_project_environment, settings  # noqa: F401
