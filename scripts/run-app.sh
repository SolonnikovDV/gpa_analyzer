#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
REQ_FILE="${ROOT_DIR}/app_gpa/requirements.txt"
ENTRYPOINT="${ROOT_DIR}/app_gpa/main.py"
APP_HOST="${FLASK_HOST:-0.0.0.0}"
APP_PORT="${FLASK_PORT:-8003}"

if [[ "${APP_HOST}" == "0.0.0.0" ]]; then
  APP_BROWSER_HOST="localhost"
else
  APP_BROWSER_HOST="${APP_HOST}"
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "[gpa] creating virtualenv at ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
fi

PYTHON_BIN="${VENV_DIR}/bin/python"

echo "[gpa] installing dependencies from ${REQ_FILE}"
"${PYTHON_BIN}" -m pip install -r "${REQ_FILE}"

echo "[gpa] starting app via ${ENTRYPOINT}"
echo "[gpa] app page: http://${APP_BROWSER_HOST}:${APP_PORT}/"
echo "[gpa] api docs: http://${APP_BROWSER_HOST}:${APP_PORT}/api/docs"
exec "${PYTHON_BIN}" "${ENTRYPOINT}"
