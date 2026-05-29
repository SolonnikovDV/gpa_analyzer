#!/usr/bin/env bash
# DCI vector store helper v8: windows + project EV namespaces
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT}/.cursor/dci/docker-compose.yml"
ENV_FILE="${ROOT}/.cursor/dci/dci.env"
SYNC_PY="${ROOT}/scripts/dci_vector_sync.py"
PY="${ROOT}/.venv/bin/python"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
elif [[ -f "${ROOT}/.cursor/dci/dci.env.example" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ROOT}/.cursor/dci/dci.env.example"
  set +a
fi

cmd="${1:-status}"
shift || true

case "${cmd}" in
  up)
    docker compose -f "${COMPOSE_FILE}" up -d
    echo "Waiting for pgvector health..."
    for _ in $(seq 1 45); do
      if "${PY}" "${SYNC_PY}" status 2>/dev/null | grep -q "pgvector: ok"; then
        break
      fi
      sleep 2
    done
    echo "Waiting for TEI health..."
    for _ in $(seq 1 90); do
      if "${PY}" "${SYNC_PY}" status 2>/dev/null | grep -q "tei: ok"; then
        break
      fi
      sleep 2
    done
    "${PY}" "${SYNC_PY}" sync --migrate --all "$@"
    ;;
  down)
    docker compose -f "${COMPOSE_FILE}" down "$@"
    ;;
  status)
    docker compose -f "${COMPOSE_FILE}" ps 2>/dev/null || true
    "${PY}" "${SYNC_PY}" status
    ;;
  sync)
    "${PY}" "${SYNC_PY}" sync --migrate "$@"
    ;;
  migrate)
    "${PY}" "${SYNC_PY}" migrate "$@"
    ;;
  export)
    "${PY}" "${SYNC_PY}" export "$@"
    ;;
  import)
    "${PY}" "${SYNC_PY}" import --source "${1:?bundle path required}" "${@:2}"
    ;;
  lookup)
    "${PY}" "${SYNC_PY}" lookup --query "${1:?query required}" "${@:2}"
    ;;
  catalog)
    mode="all"
    if [[ "${1:-}" == "--branches" ]]; then
      mode="branches"
      shift
    elif [[ "${1:-}" == "--windows" ]]; then
      mode="windows"
      shift
    fi
    "${PY}" "${SYNC_PY}" catalog --mode "${mode}" "$@"
    ;;
  window-new)
    "${PY}" "${SYNC_PY}" window-new --summary "${*:-New dialog window}"
    ;;
  restore)
    wid="${1:?window id required, e.g. DW-001}"
    shift || true
    "${PY}" "${SYNC_PY}" restore --window "${wid}" --migrate "$@"
    ;;
  compress)
    "${PY}" "${SYNC_PY}" compress "$@"
    ;;
  validate)
    "${PY}" "${SYNC_PY}" validate "$@"
    ;;
  windows)
    "${PY}" "${SYNC_PY}" windows "$@"
    ;;
  projects)
    "${PY}" "${SYNC_PY}" projects "$@"
    ;;
  restore-new)
    "${PY}" "${SYNC_PY}" user-restore --window "новое" --summary "${*:-New dialog window}"
    ;;
  *)
    echo "Usage: $0 {compress|validate|windows|projects|restore|restore-new|up|down|status|...}" >&2
    exit 1
    ;;
esac
