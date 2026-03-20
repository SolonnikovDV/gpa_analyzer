# Operations Runbook

Минимальный runbook для production-like запуска на хосте (без контейнеров) и базовой диагностики.

## Stack

- **web**: Flask-приложение (или Gunicorn)
- **worker**: RQ worker для фоновых job'ов (при `JOB_RUNNER_BACKEND=queue`)
- **redis**: брокер очереди (при queue backend)
- **sqlite**: persistence для job state, логов и presets

## Start

При запуске с `FLASK_DEBUG=false` **обязательно** задать `APP_SECRET_KEY`; иначе приложение при старте выбросит ошибку.

1. Запустить Redis (если используется queue backend):

```bash
redis-server
# или: brew services start redis
```

2. Задать переменные и запустить web:

```bash
cd app_gpa
export APP_SECRET_KEY='replace-with-long-random-secret'
export JOB_RUNNER_BACKEND=queue
export REDIS_URL=redis://localhost:6379/0
export RUNTIME_STORE_DIR=.runtime_store
export PERSISTENCE_DB_PATH=.runtime_store/app_state.sqlite3
python webapp.py
# или: gunicorn --bind 0.0.0.0:8003 --workers 2 --timeout 120 webapp:app
```

3. В отдельном терминале запустить worker (при queue backend):

```bash
cd app_gpa
export APP_SECRET_KEY='replace-with-long-random-secret'
export JOB_RUNNER_BACKEND=queue
export REDIS_URL=redis://localhost:6379/0
export PERSISTENCE_DB_PATH=.runtime_store/app_state.sqlite3
python worker.py
```

Проверка (порт по умолчанию 8000 или 8003 при gunicorn):

```bash
curl -s http://localhost:8000/health/live
curl -s http://localhost:8000/health/ready
```

## Smoke check (после изменений)

Запустить web (и при необходимости Redis + worker), затем:

```bash
curl -sf http://localhost:8000/health/live && echo " live OK"
curl -sf http://localhost:8000/health/ready && echo " ready OK"
```

## Stop

Остановить процессы web и worker (Ctrl+C или SIGTERM). При использовании Redis — при необходимости остановить и его.

## Logs

Логи пишутся в stdout/stderr процессов web и worker. При необходимости перенаправить в файлы или в систему логирования на хосте.

## Health Diagnostics

- **`/health/live`** — процесс отвечает. Всегда 200 при работающем приложении.
- **`/health/ready`** — проверка SQLite; при `JOB_RUNNER_BACKEND=queue` также проверка Redis. При недоступности зависимостей возвращает **503** и `"status": "degraded"`.

Если `/health/ready` возвращает `degraded`:

1. Проверить логи web-процесса.
2. Убедиться, что Redis запущен и доступен по `REDIS_URL` (при queue backend).
3. Проверить права на каталог и файл SQLite (`PERSISTENCE_DB_PATH`).

## Common Incidents

### 1. Web отвечает, но job'ы не исполняются

- Убедиться, что `JOB_RUNNER_BACKEND=queue`, Redis запущен, worker запущен в отдельном процессе.
- Проверить логи worker'а.

### 2. `/health/ready` degraded из-за Redis

- Запустить Redis или проверить `REDIS_URL`.
- Перезапустить web и worker после появления Redis.

### 3. SQLite недоступен или повреждён

- Проверить существование каталога и файла по `PERSISTENCE_DB_PATH`.
- Проверить права на запись.

### 4. APP_SECRET_KEY не задан

В non-debug режиме приложение не стартует с плейсхолдерным ключом. Задать:

```bash
export APP_SECRET_KEY='replace-with-long-random-secret'
```

## Backup

Скопировать файл SQLite состояния:

```bash
cp .runtime_store/app_state.sqlite3 .runtime_store/app_state.sqlite3.backup
```

Рекомендуется останавливать или не нагружать приложение на время копирования.

## Restore

Остановить web и worker, заменить `app_state.sqlite3` из backup, запустить снова.

## Current Limitations

- SQLite подходит для baseline и single-node deployment, но не для полноценного HA production.
- Rate limiting in-memory и не распределён между несколькими web-инстансами.
- Structured logs идут в stdout/stderr; отдельный log shipping не описан.
- Контейнеризация (Docker) пока не используется.
