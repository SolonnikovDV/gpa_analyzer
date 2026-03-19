# Production Roadmap

Этот документ фиксирует последовательный план доведения проекта до production-ready состояния без лишнего overengineering. Идем по фазам сверху вниз и не прыгаем к следующим шагам, пока не закрыт предыдущий блок.

## Phase 0. Freeze Scope
Цель: зафиксировать границы первого production релиза.

- Определить обязательный стек первого релиза: `GreenPlum`.
- Зафиксировать статус `Spark` и `PySpark` как ограниченно поддерживаемых runtime'ов.
- Зафиксировать обязательные пользовательские сценарии:
  - SQL validation
  - discover/analyze
  - hybrid flow
  - pure agent flow
  - runtime presets
- Зафиксировать non-goals первого релиза.
- Зафиксировать минимальные эксплуатационные требования:
  - максимальная длительность job
  - число одновременных job
  - базовые ожидания к recoverability

## Phase 1. Stabilize Core Architecture
Цель: сделать кодовую базу предсказуемой и пригодной для hardening.

- Вынести app/env configuration из `webapp.py` в отдельный settings layer.
- Зафиксировать основные слои:
  - routes/controller
  - orchestration
  - analyzers
  - lint/completion
  - persistence
- Ввести единые контракты для:
  - job payload
  - job status
  - discovery result
  - analysis result
  - runtime preset payload
- Свести прямые мутации job state к сервисному слою.
- Зафиксировать error codes и базовые response contracts.

## Phase 2. Production Background Jobs
Цель: убрать зависимость от `in-process threads`.

- Выбрать backend для очередей и worker'ов.
- Разделить web process и worker process.
- Добавить timeout policy.
- Добавить retry policy.
- Добавить cancellation/recovery semantics.
- Перевести job execution lifecycle на очередь.

## Phase 3. Persistent Storage
Цель: заменить локальные файлы на production-grade state storage.

- Выбрать основную БД приложения.
- Ввести migrations.
- Спроектировать таблицы для:
  - jobs
  - job logs/events
  - runtime presets
  - service metadata
- Ввести retention policy.
- Исключить секреты из persisted payload.

## Phase 4. Security Baseline
Цель: сделать систему безопасной для реального использования.

- Ввести auth/authz слой.
- Централизовать работу с секретами.
- Маскировать секреты в логах и ошибках.
- Добавить request limits и payload limits.
- Проверить ingest/import пути на abuse cases.
- Настроить session/cookie security.

## Phase 5. API and Contract Hardening
Цель: сделать API стабильным и формально валидируемым.

- Ввести схемы валидации request/response payload.
- Зафиксировать job state machine.
- Унифицировать ошибки в единый формат.
- Версионировать критичные API.
- Зафиксировать stack/scenario capability matrix как явный контракт.

## Phase 6. Automated Testing
Цель: подтвердить стабильность изменений автоматическими проверками.

- Unit tests для registry, linters, analyzers, services.
- Integration tests для API endpoints.
- E2E tests для ключевых UI flows.
- Regression fixtures для SQL, metadata/profile JSON и failure paths.
- CI pipeline с обязательными проверками.

## Phase 7. Observability
Цель: упростить диагностику и поддержку production среды.

- Structured logging.
- Correlation IDs для request/job.
- Метрики job execution и failures.
- Healthcheck endpoints.
- Alerting на критичные деградации.

## Phase 8. Deployment and Operations
Цель: сделать релизы и поддержку воспроизводимыми.

- ~~Production containers~~ — пока не требуется, приложение запускается на хосте.
- Reverse proxy и TLS (при необходимости).
- Release/rollback process.
- DB backup/restore.
- Runbooks для эксплуатации (OPERATIONS_RUNBOOK.md — запуск без контейнеров).

## Current Execution Order

1. Phase 0: зафиксировать scope первого релиза.
2. Phase 1: стабилизировать конфигурацию и контракты.
3. Phase 2: заменить thread-based jobs на очередь.
4. Phase 3: перевести persistence в БД.
5. Phase 4-8: безопасность, API hardening, тесты, observability, deployment.

## Current Focus

- Завершено: settings layer вынесен из `webapp.py`.
- Завершено: job status contracts зафиксированы.
- Завершено: добавлен runner factory и execution metadata.
- Завершено: подключен первый production queue backend на `Redis + RQ`.
- Завершено: persistence переведен с файлового job/preset storage на SQLite.
- Завершено: внедрен базовый security baseline для secret masking, cookie/session config и request limits.
- Завершено: добавлен минимальный auth/authz и rate limiting baseline.
- Завершено: базовый Phase 5, унификация API contracts и request validation для ключевых endpoints.
- Завершено: минимальный automated testing baseline для contracts, validation, limiter и SQLite stores.
- Завершено: integration API tests для ключевых contract-safe endpoints.
- Завершено: базовый CI/test workflow для автоматического прогона `pytest`.
- Завершено: observability baseline с structured logging, request/job correlation и health endpoints.
- Завершено: deployment/operations baseline через runbook (без контейнеров; Docker/compose удалены по требованию).
- Завершено: финальный production-hardening pass.
  - Блокировка старта при плейсхолдерном `APP_SECRET_KEY` в non-debug режиме.
  - Runbook переведён на запуск на хосте (web, worker, Redis, SQLite); smoke check и диагностика по health endpoints.
  - Автоматический smoke по health покрыт интеграционными тестами.
