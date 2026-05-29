#!/usr/bin/env bash
# Копирует изменения из текущего worktree в каталог PyCharm (полный путь).
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DST="${PYCHARM_PROJECT:-$HOME/PycharmProjects/overhead_analyzer}"

if [[ ! -d "$DST" ]]; then
  echo "Целевой каталог не найден: $DST" >&2
  exit 1
fi

echo "Источник: $SRC"
echo "Назначение: $DST"
rsync -a --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude 'tig_snapshot.md' \
  --exclude 'tig_delta.md' \
  "$SRC/app_gpa/" "$DST/app_gpa/"
rsync -a "$SRC/.cursor/rules/" "$DST/.cursor/rules/" 2>/dev/null || true
echo "Готово."
