#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
REQ_FILE="${ROOT_DIR}/app_gpa/requirements.txt"
ENTRYPOINT="${ROOT_DIR}/app_gpa/main.py"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "[gpa] creating virtualenv at ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
fi

PYTHON_BIN="${VENV_DIR}/bin/python"

echo "[gpa] installing dependencies from ${REQ_FILE}"
"${PYTHON_BIN}" -m pip install -r "${REQ_FILE}"

echo "[gpa] starting app via ${ENTRYPOINT}"
exec "${PYTHON_BIN}" "${ENTRYPOINT}"
