# GPA Analyzer

**Оценка нагрузки и рисков выполнения PL/pgSQL-функций в Greenplum по планам запросов.**

> Architecture overview → [`project_doc/index.md`](project_doc/index.md)

Приложение анализирует DDL функции, извлекает SQL-блоки, подставляет параметры и переменные, выполняет `EXPLAIN` для каждого блока и оценивает пиковую нагрузку на память сегментов кластера. Распространяется по лицензии [MIT](LICENSE).

---

## Описание приложения

GPA Analyzer — веб-приложение для предварительной оценки того, как выполнение PL/pgSQL-функции в Greenplum нагрузит кластер. Оно:

- **Обнаруживает таблицы** в теле функции (включая представления и временные таблицы) и при наличии подключения к БД запрашивает текущие размеры (строки, средняя ширина строки, оценка в GB).
- **Позволяет задать желаемые размеры** таблиц (например, для сценария роста данных) и параметры вызова функции.
- **Строит планы** (`EXPLAIN`) для каждого рабочего SQL-блока с подставленными значениями, применяет пользовательские размеры к планам и оценивает нагрузку по типам узлов плана (множители для Seq Scan, Hash Join, Sort и т.д.).
- **Суммирует нагрузку** по всем блокам и выдаёт итоговую оценку: общий объём (GB), уровень риска (низкий / средний / высокий) и оценочное время выполнения.
- **Детектирует антипаттерны** (LATERAL с ORDER BY + LIMIT 1, CROSS JOIN, коррелированные подзапросы, SELECT DISTINCT и др.) и применяет множители нагрузки на скейле данных.
- **Поддерживает режим без БД** (чистый агент): агент извлекает блоки и объекты, синтезирует планы. Для больших скриптов — чанкинг и повторные попытки при таймауте.
- **GigaChat:** одна выбранная чат-модель и одна модель эмбеддингов на вызов (UI / `GIGACHAT_*` / значение по умолчанию); в UI — информационная проверка доступности моделей и отображение имён на шагах подготовки, настройки таблиц и в итоге анализа.

Интерфейс: форма ввода DDL, опциональное подключение к Greenplum, пошаговый лог в реальном времени, таблицы с результатами и топ запросов по нагрузке.

---

## Установка и настройка

### Требования

- Python 3.9+
- Доступ к кластеру Greenplum (опционально; без него можно задавать только размеры таблиц вручную).

### Зависимости

Установите зависимости из `app_gpa/requirements.txt`:

```bash
cd app_gpa
pip install -r requirements.txt
```

Основные пакеты:

| Пакет | Назначение |
|-------|------------|
| flask | Веб-сервер и маршруты |
| psycopg2-binary | Подключение к PostgreSQL/Greenplum |
| psutil | Мониторинг ресурсов (CPU, память) при расчёте |
| pglast | Парсинг SQL и извлечение объектов (таблицы, представления) |
| gigachat | GigaChat API: извлечение блоков/объектов, синтез планов (режим агента) |

### Запуск

Единый запуск на любой машине (рекомендуется):

```bash
bash scripts/run-app.sh
```

Скрипт сам:
- создаёт `.venv` (если нет),
- устанавливает зависимости из `app_gpa/requirements.txt`,
- запускает `app_gpa/main.py` (FastAPI + Flask hybrid).

По умолчанию приложение слушает `http://0.0.0.0:8003`. Откройте в браузере `http://localhost:8003` или `http://localhost:8003/detailed`.

### Production queue backend

Для production можно переключить выполнение фоновых job'ов с локальных потоков на `Redis + RQ`.

Пример переменных окружения:

```bash
export JOB_RUNNER_BACKEND=queue
export REDIS_URL=redis://localhost:6379/0
export JOB_QUEUE_NAME=gpa-jobs
```

Запуск web-приложения:

```bash
bash scripts/run-app.sh
```

Legacy fallback (только Flask, для отладки совместимости):

```bash
cd app_gpa
python webapp.py
```

Запуск worker-процесса:

```bash
cd app_gpa
python worker.py
```

Если `JOB_RUNNER_BACKEND` не задан, приложение использует текущий режим `thread`, удобный для локальной разработки.

### DB-backed persistence

Состояние job'ов, логи и runtime presets теперь можно хранить в SQLite вместо файлового каталога.

Пример:

```bash
export RUNTIME_STORE_DIR=.runtime_store
export PERSISTENCE_DB_PATH=.runtime_store/app_state.sqlite3
```

По умолчанию база создается автоматически по пути `RUNTIME_STORE_DIR/app_state.sqlite3`.
При первом запуске сервис пытается мягко перенести legacy-данные из старых файловых store в SQLite.

### Security baseline

Для non-debug запуска задайте безопасный `APP_SECRET_KEY`. В режиме `FLASK_DEBUG=false` приложение не стартует с дефолтным ключом.

Полезные переменные окружения:

```bash
export APP_SECRET_KEY='replace-with-long-random-secret'
export MAX_CONTENT_LENGTH_BYTES=2097152
export SESSION_COOKIE_SECURE=true
export SESSION_COOKIE_HTTPONLY=true
export SESSION_COOKIE_SAMESITE=Lax
export SESSION_LIFETIME_MINUTES=120
```

### Minimal auth and rate limiting

Для базовой защиты production-инстанса можно включить HTTP Basic Auth и простое ограничение частоты запросов:

```bash
export APP_BASIC_AUTH_USERNAME=admin
export APP_BASIC_AUTH_PASSWORD='replace-with-strong-password'
export RATE_LIMIT_ENABLED=true
export RATE_LIMIT_REQUESTS=120
export RATE_LIMIT_WINDOW_SECONDS=60
```

Особенности текущего baseline:

- Basic Auth применяется глобально ко всем non-static routes.
- Rate limiting применяется на web-слое по IP-адресу клиента.
- Это минимальный baseline, а не полноценная IAM/SSO-схема.

### Automated tests

Минимальный test baseline запускается из каталога `app_gpa`:

```bash
cd app_gpa
python -m pytest
```

Покрытый минимум:

- API contract helpers
- request validation helpers
- in-memory rate limiter
- SQLite job/preset stores
- Flask integration endpoints для contract-safe API
- выбор одной чат-/embedding-модели GigaChat (`app_gpa/tests/test_gigachat_model_fallback.py`)

CI:

- GitHub Actions workflow: `.github/workflows/python-tests.yml`
- Workflow устанавливает зависимости из `app_gpa/requirements.txt` и запускает `python -m pytest`

### Observability baseline

В приложении включён минимальный observability baseline:

- `X-Request-ID` выставляется в ответах и может быть передан извне через заголовок запроса
- structured logs пишутся для:
  - начала/завершения HTTP request
  - rate limiting / unauthorized событий
  - создания, enqueue и completion/failure job'ов
- health endpoints:
  - `/health/live`
  - `/health/ready`
  - `/health`

`/health/ready` проверяет как минимум SQLite persistence. Если включён queue backend, дополнительно проверяется доступность Redis.

Приложение пока не упаковывается в контейнеры; запуск — процессы на хосте (см. разделы выше: web, worker, Redis, persistence). Операционные процедуры и диагностика описаны в `OPERATIONS_RUNBOOK.md`.

### Настройка подключения к БД

На странице «Детальный анализ» можно включить «Использовать подключение к БД» и указать:

- **Стенд** — пресет (PROM, LD, IFT) или свои Host, Port, DB name.
- **User** и **Password** — учётные данные Greenplum.

Без подключения приложение работает только с введённым вручную DDL и размерами таблиц (без автоматического получения статистики из БД).

### Режим агента (GigaChat API)

В разделе **«Способ выполнения аналитики»** можно выбрать **«Режим агента»**: генерация SQL или DDL функции по текстовому описанию через [GigaChat API](https://developers.sber.ru/docs/ru/gigachain/overview) (GigaChain).

**Режимы анализа:**

| Режим | Описание |
|-------|----------|
| **Только логика** | Парсер извлекает блоки и объекты из DDL, планы берутся из БД (EXPLAIN). Требуется подключение к БД. |
| **Гибрид** | С БД: парсер + EXPLAIN в БД; при ошибках — агент (DDL по объектам, синтез планов). Без БД: чистый агент. |
| **Чистый агент** | Агент сам извлекает блоки и объекты из DDL/SQL, синтезирует планы. БД не требуется. Поддерживает PL/pgSQL функции, один SQL-запрос и скрипты (DDL/DML). |

**Чистый агентский режим:** агент интерпретирует тип ввода (функция, запрос или скрипт), извлекает блоки и объекты, синтезирует планы. Для больших текстов (>35k символов) используется чанкинг с таймаутом и повторными попытками. Временные таблицы и наследование определяются агентом по контексту.

**Настройка:**

1. Получите ключ авторизации в [личном кабинете GigaChat API](https://developers.sber.ru/studio/) (проект → Настройки).
2. Задайте ключ одним из способов:
   - **В UI:** режим «Гибрид» → «Ввести ключ» (ключ не сохраняется — только в памяти до перезагрузки страницы)
   - **В .key:** создайте файл `.key` в корне проекта, первая строка — токен base64 (для профиля «разработчик»).
   - **В .env:** `GIGACHAT_CREDENTIALS=<ключ>` или `GIGACHAT_TOKEN=<ключ>`.

   Пример файла `.key` (корень проекта):
   ```
   ваш_base64_токен_из_личного_кабинета
   ```
   Или несколько строк (токен — строка, похожая на base64, ≥32 символов):
   ```
   client_id
   GIGACHAT_API_PERS
   ваш_base64_токен
   ```

   Альтернатива: `GIGACHAT_CLIENT_ID` + `GIGACHAT_CLIENT_SECRET` в .env (приложение соберёт credentials автоматически).
3. Опционально в .env:
   - `GIGACHAT_MODEL` — чат-модель по умолчанию, если в запросе/UI не передано другое имя. Если не задано — используется `GigaChat-2-Max` (см. [модели GigaChat](https://developers.sber.ru/docs/ru/gigachat/models/gigachat-2-max)). Перебора моделей при ошибке API нет.
   - `GIGACHAT_EMBEDDING_MODEL` — модель эмбеддингов по умолчанию; если не задано — `EmbeddingsGigaR` ([документация](https://developers.sber.ru/docs/ru/gigachat/models/embeddings-giga-r)).
   - `GIGACHAT_SCOPE` — версия API: `GIGACHAT_API_PERS` (физлица), `GIGACHAT_API_B2B`, `GIGACHAT_API_CORP`.
   - `GIGACHAT_VERIFY_SSL_CERTS=false` — отключить проверку SSL (если не установлены сертификаты Минцифры).
   - `GIGACHAT_HTTP_TIMEOUT_SEC` — таймаут HTTP-клиента Python SDK (сек.) для всех вызовов GigaChat (chat, embeddings, OAuth-запросы через тот же клиент). По умолчанию **180**; если не задано, используется `GIGACHAT_TIMEOUT_SEC`, иначе 180. Без этого у SDK часто **30 с** и обрыв генерации с «The read operation timed out».
   - `GIGACHAT_TIMEOUT_SEC` — таймаут синтеза плана в отдельном потоке (по умолчанию 120 с); также подставляется как HTTP-таймаут, если не задан `GIGACHAT_HTTP_TIMEOUT_SEC`.
   - `GIGACHAT_BLOCKS_TIMEOUT_SEC` — таймаут извлечения блоков и объектов (по умолчанию 180 с).

Проверка списка моделей из UI (простой `chat` и `embeddings` на каждое имя из `CHAT_MODEL_PRIORITY` / `EMBEDDING_MODEL_PRIORITY`), при валидном ключе:

```bash
.venv/bin/python app_gpa/validate_gigachat_models.py
```

(используйте интерпретатор из venv проекта, где установлен пакет `gigachat`).

Учёт токенов в приложении опирается на официальные методы GigaChat:
- **Остаток:** [GET /balance](https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/get-balance) (доступен при пакетах токенов; при pay-as-you-go часто **403** — тогда в UI показывается оценка по лимиту Lite Freemium).
- **Подсчёт до запроса:** [POST /tokens/count](https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/post-tokens-count) — обёртка `POST /api/agent/tokens_count` (тело JSON: `input` — массив строк, опционально `model`, `credentials`, `scope`).

#### Справочные списки моделей и один выбор на вызов

В коде заданы упорядоченные списки имён (для UI и для **«Проверить доступность»** — там по очереди опрашивается каждая модель):

| Тип | Порядок имён (справочно) |
|-----|--------------------------|
| **Чат** | `GigaChat-2-Max` → `GigaChat-2-Pro` → `GigaChat-2` (значения поля `model`, [гайд](https://developers.sber.ru/docs/ru/gigachat/guides/selecting-a-model); лёгкий тариф — `GigaChat-2`, не `GigaChat-2-Lite`) |
| **Эмбеддинги** | `EmbeddingsGigaR` → `GigaEmbeddings-3B-2025-09` → `Embeddings-2` → `Embeddings` |

- Рабочие вызовы API используют **ровно одну** чат-модель и **одну** модель эмбеддингов: приоритет — поле из запроса/UI, затем **`GIGACHAT_MODEL`** / **`GIGACHAT_EMBEDDING_MODEL`**, затем первая строка из соответствующего списка.
- Для job в discovery/analyze передаётся выбранная чат-модель (см. ниже); она имеет приоритет над `GIGACHAT_MODEL`.

#### Выбор моделей в окне профиля GigaChat

В модальном окне **«Ключ GigaChat API»** задаются поля **«Чат-модель»** и **«Модель эмбеддингов»** (список имён совпадает со справочными списками в коде). После **«Применить»**:

- выбор сохраняется в **`localStorage`** браузера (`gpa_agent_chat_model`, `gpa_agent_embedding_model`) и в записи профиля в **`agent_profiles.json`** (поля `chatModel`, `embeddingModel`), если выбран или создан именованный профиль;
- при следующем открытии окна можно **сменить модели**; последний выбранный профиль подставляется по ключу `gpa_agent_last_profile_name` в `localStorage`;
- скрытые поля формы `agent_chat_model` / `agent_embedding_model` уходят на сервер с **«Обнаружить таблицы»** / анализом — попадают в **job** и в **`/status/<job_id>`**.

Кнопка **«Проверить доступность»** открывает **информационный модал**: по API проверяется ответ по каждой модели (✓/✗); он **не подменяет** выбранные в окне профиля значения — только подсказка.

**Где видны выбранные модели:** полоска на шаге **1. Подготовка**, бейдж в шапке лога на шаге **2**, бейдж в сводке на странице **результата**; в логе анализа — строка о выбранных моделях.

#### API: списки моделей и проверка доступности

`GET /api/agent/model-options` — в `data`: массивы имён `chat` и `embedding` (как `CHAT_MODEL_PRIORITY` / `EMBEDDING_MODEL_PRIORITY` в `gigachat_agent.py`).

`POST /api/agent/probe-models` — тело JSON (часть полей опциональна):

- `credentials` — base64-токен; либо пара `client_id` + `client_secret` (соберётся в credentials на сервере);
- если ключа в теле нет — используется `.key` / `.env` на сервере (как у `validate-env`); `use_env_credentials: true` по-прежнему может отправлять UI для явного указания режима;
- `scope` — например `GIGACHAT_API_PERS`;
- `verify_ssl` — boolean, переопределяет проверку SSL для этого запроса.

Успешный ответ (формат contract-safe API, данные в `data`): массивы `chat` и `embedding` с элементами `{ "model", "ok", "error" }`, поля `selected_chat`, `selected_embedding`, а также `chat_priority` и `embedding_priority` — полные цепочки, как в коде.

`POST /api/agent/generate` (генерация SQL/DDL по описанию) дополнительно принимает **`chat_model`** или **`agent_chat_model`** — чат-модель для этого вызова (приоритет над `GIGACHAT_MODEL`).

Документация: [Python SDK](https://developers.sber.ru/docs/ru/gigachain/tools/python/gigachat), [выбор модели](https://developers.sber.ru/docs/ru/gigachat/guides/selecting-a-model). Для RAG можно установить `langchain-gigachat` (см. комментарии в `app_gpa/requirements.txt`).

---

## Инструкция по работе с приложением

### Шаг 1. Открытие приложения

1. Запустите сервер (`bash scripts/run-app.sh` из корня репозитория).
2. В браузере откройте `http://localhost:8003` — откроется страница **«Детальный анализ»**.

### Шаг 2. Выбор режима и ввод DDL

1. **Режим анализа:** выберите один из трёх:
   - **Только логика** — нужна БД, планы из EXPLAIN.
   - **Гибрид** — с БД или без; при «без БД» автоматически чистый агент.
   - **Чистый агент** — без БД, нужен ключ GigaChat («Ввести ключ» или .key/.env).
2. **GigaChat (гибрид / агент):** в окне **«Ввести ключ»** выберите **чат-модель** и **embedding-модель**, нажмите **«Применить»** — выбор запоминается в браузере и в профиле (`agent_profiles.json`). При следующем открытии окна модели можно изменить. Опционально: **«Проверить доступность»** — только справка по ответам API.
3. **В поле «DDL функции»** вставьте:
   - PL/pgSQL функцию (CREATE OR REPLACE FUNCTION … AS $$ … $$ LANGUAGE plpgsql), или
   - один SQL-запрос (SELECT/INSERT/UPDATE/DELETE), или
   - скрипт (несколько DDL/DML). Агент сам определит тип.
4. При необходимости нажмите **«Подсказки»** — краткая справка по режимам и заполнению.

### Шаг 3. Подключение к БД (опционально)

- Если нужны **текущие размеры таблиц из кластера**: включите чекбокс **«Использовать подключение к БД»**.
- Укажите **Стенд** (пресет) или вручную **Host**, **Port**, **DB name**, **User**, **Password**.
- Если БД не используется — размеры таблиц потом задаются только вручную на шаге 6.

### Шаг 4. Параметры кластера

- **Количество сегментов** и **RAM на сегмент (GB)** — используются для расчёта нагрузки и риска. Подставьте значения вашего кластера или оставьте по умолчанию.

### Шаг 5. Обнаружение таблиц (первый этап)

1. Нажмите **«Обнаружить таблицы»**.
2. Произойдёт переход на страницу с **онлайн-логом** и индикатором «Сканирование таблиц…».
3. В логе отображаются: разбор блоков, извлечённые таблицы, при наличии БД — запросы размеров. Дождитесь статуса **«tables_discovered»** (зелёный бейдж). Если расчёт шёл через агентный контур, в шапке лога может отображаться **бейдж GigaChat** с чат- и embedding-моделью этого job.
4. Появится форма **«Настройка размеров таблиц и параметров функции»**.

### Шаг 6. Параметры функции и размеры таблиц

1. **Параметры функции** — введите значения параметров вызова в том же порядке, что и в сигнатуре функции, через запятую. Например: `'2024-01-01', 'current_date', 5`. Для строк — в кавычках.
2. В таблице **«Найденные таблицы»** проверьте столбец **«Желаемое строк»**: по умолчанию подставлено текущее (из БД) или 0. При необходимости измените значения (например, для сценария роста данных).
3. Нажмите **«Запустить анализ нагрузки»**.

### Шаг 7. Просмотр результата анализа (второй этап)

1. Откроется страница **«Результат детального анализа»** с логом и блоком **«Краткая статистика»**.
2. В логе в реальном времени выводятся обработанные блоки и возможные предупреждения. Дождитесь завершения (статус **«done»**).
3. При использовании GigaChat в сводке может отображаться **бейдж с именами чат- и embedding-модели**, зафиксированными для этого расчёта.
4. После завершения появятся:
   - **Панель ключевых метрик** — риск, нагрузка (GB), число блоков, оценочное время. При наличии антипаттернов — «+X GB антипаттерны».
   - **Вкладки**: «Таблицы», «Блоки», «Топ-3 запроса», «Статистика выполнения». В блоках с антипаттернами — бейдж с предупреждением.
5. Кнопка **«Копировать весь лог»** копирует содержимое лога в буфер обмена.

### Шаг 8. Пересчёт с другими размерами таблиц (опционально)

1. На вкладке **«Таблицы»** измените значения в столбце **«Желаемое строк»**.
2. Нажмите **«Применить размеры и пересчитать»** — анализ запустится заново с новыми размерами (параметры функции сохраняются).

### Краткая схема

| Действие | Страница / элемент |
|---------|---------------------|
| Ввод DDL, БД, параметров кластера | Детальный анализ (форма) |
| Ключ GigaChat и модели (гибрид/агент) | «Ввести ключ» → выбор моделей в окне профиля → «Применить» |
| Запуск первого этапа | Кнопка «Обнаружить таблицы» |
| Ввод параметров функции и размеров таблиц | Настройка размеров таблиц |
| Запуск второго этапа | Кнопка «Запустить анализ нагрузки» |
| Просмотр лога и сводки | Результат детального анализа |
| Пересчёт с новыми размерами | Вкладка «Таблицы» → «Применить размеры и пересчитать» |

---

## Результаты анализа и их интерпретация

После второго этапа (анализ с пользовательскими размерами) приложение выдаёт:

### Сводные показатели

| Показатель | Описание |
|------------|----------|
| **Риск** | НИЗКИЙ / СРЕДНИЙ / ВЫСОКИЙ — по доле суммарной оценки памяти от доступной RAM на сегмент (пороги: &lt;15% низкий, 15–40% средний, &gt;40% высокий). |
| **Нагрузка (GB)** | Сумма пиковых оценок памяти по всем проанализированным блокам (в GB). При наличии антипаттернов добавляется множитель (+X GB от антипаттернов на скейле). |
| **Блоков** | Количество логических блоков в теле функции и сколько из них реально проанализировано (часть блоков не считается — см. ограничения). |
| **Время (сек)** | Оценочное время выполнения (сумма по блокам на основе Total Cost плана и коэффициентов). |

### Таблицы

- **Найденные таблицы** — список таблиц/представлений из DDL с текущими (из БД) или введёнными вручную размерами: строки, размер в GB, средняя ширина строки. Можно изменить «Желаемое строк» и перезапустить анализ.

### Блоки

- Таблица блоков: тип (SELECT, INSERT, EXECUTE и т.д.), категория, оценка нагрузки (GB), строки, задействованные таблицы. Цветовая полоска слева от строки показывает уровень нагрузки (низкая / средняя / высокая). Клик по строке показывает превью SQL.

### Топ-3 запроса

- Три блока с максимальной оценкой нагрузки (GB) — основные кандидаты на оптимизацию.

### Интерпретация

- **НИЗКИЙ риск** — расчётная нагрузка в пределах нормы для типичного кластера.
- **СРЕДНИЙ / ВЫСОКИЙ** — стоит проверить тяжёлые блоки (топ-3), возможность разбиения или изменения запросов, индексов и размеров таблиц.
- Оценки основаны на планах `EXPLAIN` и эвристических множителях по типам узлов; они дают порядок величины, а не точное время и память.

---

## Ограничения анализа

Учтены типичные проблемы, с которыми сталкивались при отладке. Ниже — что приложение **учитывает** и чего **не делает**.

### Учитываемые моменты

- **SELECT … INTO** в PL/pgSQL трактуется как присвоение переменным; такие блоки **не считаются** рабочими блоками нагрузки и не отправляются в EXPLAIN. Вместо выполнения запроса переменным присваиваются безопасные значения по умолчанию (в т.ч. для агрегатов типа `min/max`).
- **EXECUTE … INTO …** (динамический SQL с записью результата в переменные) обрабатывается так же, как SELECT INTO — блок **не учитывается** в нагрузке.
- **Подстановка переменных** в SQL выполняется с защитой: целевые имена в `INTO` не подменяются значениями; литералы дат приводятся к виду `'YYYY-MM-DD'::date` без двойных кавычек; обрабатываются значения с уже имеющимся `::type`.
- **Временные таблицы** отслеживаются по `CREATE TEMP TABLE` и учитываются при сборе объектов.

### Ограничения и что может пойти не так

1. **Только часть блоков в нагрузке**  
   В расчёт попадают только блоки, которые удаётся разобрать и для которых строится EXPLAIN. Не учитываются: SELECT INTO, EXECUTE … INTO …, TRUNCATE, ANALYZE, VACUUM, блоки с неразобранным динамическим SQL, блоки с ошибкой парсинга или выполнения EXPLAIN. Поэтому «Блоков» может быть меньше, чем визуально в DDL.

2. **Динамический SQL (EXECUTE)**  
   Поддерживаются форматы `EXECUTE '...' USING a, b` и `EXECUTE format('...', a, b)` с подстановкой переменных. Сложные конкатенации строк, условная сборка запроса или неподдерживаемые плейсхолдеры могут привести к тому, что блок будет пропущен или подставленный SQL окажется некорректным.

3. **Типы данных и литералы**  
   Подстановка параметров и переменных ориентирована на типы date, timestamp, varchar, integer и т.п. Экзотические типы, кастомные приведения или сложные выражения могут дать неверный литерал в SQL и ошибку при EXPLAIN.

4. **Агрегаты в SELECT INTO**  
   Для `SELECT min(col), max(col) INTO v1, v2 FROM t` запрос к БД не выполняется; переменным присваиваются дефолтные значения (например, даты по умолчанию). Реальные min/max из данных в оценку не входят.

5. **Функции, отсутствующие в Greenplum**  
   Если в подставленном SQL вызывается функция, которой нет в кластере (например, `round(double precision, integer)`), EXPLAIN может вернуть ошибку и блок будет пропущен.

6. **Парсер pglast**  
   Извлечение таблиц/представлений и обход плана зависят от pglast. Нестандартный или невалидный SQL может не распарситься; при смене версии pglast возможны изменения в AST (например, имена узлов).

7. **Один сценарий на запуск**  
   Оценка делается для одного набора параметров функции и одного набора размеров таблиц. Сравнение нескольких сценариев требует нескольких запусков.

8. **Оценка по плану, не по факту**  
   Используется только план запроса (cost, rows, width) и множители по типам узлов. Реальное потребление памяти и время выполнения могут отличаться (статистика, skew, конкуренция за ресурсы).

---

## Техническая часть

### Структура проекта

```
overhead_analyzer/
├── LICENSE
├── README.md
└── app_gpa/
    ├── webapp.py              # Flask: маршруты, очереди логов, запуск задач
    ├── requirements.txt
    ├── static/
    │   ├── styles.css         # Общие стили, лог, формы
    │   └── detailed.css       # Загрузка, системная статистика
    ├── templates/
    │   ├── about_modal.html   # О приложении, лицензия MIT
    │   └── tips_modal.html   # Подсказки по форме
    ├── agent/
    │   ├── gigachat_agent.py    # GigaChat: блоки/объекты, синтез планов
    │   └── agent_prompts.py    # Промпты для агента
    └── detailed/
        ├── detailed_analyzer.py  # Ядро: discover_tables, analyze_with_user_sizes
        ├── block_parser.py       # Разбиение PL/pgSQL на блоки, классификация
        ├── sql_object_extractor.py  # pglast: извлечение таблиц/представлений из SQL
        ├── execute_parser.py    # EXECUTE format/USING, SELECT INTO
        ├── nested_block_extractor.py  # Вложенные SQL-блоки
        ├── antipattern_detector.py  # Детекция антипаттернов, множители нагрузки
        ├── load_calculator.py   # Оценка нагрузки по плану (множители узлов)
        ├── plan_adjuster.py     # Подстановка пользовательских размеров в план
        ├── temp_table_tracker.py
        ├── performance_monitor.py  # CPU/память процесса
        └── templates/
            ├── detailed_input.html   # Форма DDL, БД
            ├── table_sizes.html     # Результат discovery, форма размеров и параметров
            └── detailed_result.html # Лог, сводка, вкладки (таблицы, блоки, топ-3)
```

### Связи объектов (компоненты и зависимости)

Основные модули приложения и их зависимости:

```mermaid
graph TB
    subgraph Web["Веб-слой"]
        webapp[webapp.py]
        webapp --> discover_route["/detailed/discover"]
        webapp --> analyze_route["/detailed/analyze"]
        webapp --> stream_route["/stream/<job_id>"]
        webapp --> status_route["/status/<job_id>"]
    end

    subgraph Analyzer["Ядро анализа"]
        analyzer[DetailedGreenplumFunctionAnalyzer]
        analyzer --> discover_tables[discover_tables]
        analyzer --> analyze_with_sizes[analyze_with_user_sizes]
    end

    subgraph Parsing["Парсинг и извлечение"]
        block_parser[block_parser]
        sql_extractor[SQLObjectExtractor]
        execute_parser[ExecuteParser]
        nested_extractor[NestedBlockExtractor]
        temp_tracker[TempTableTracker]
        antipattern[antipattern_detector]
    end

    subgraph Calculation["Расчёт нагрузки"]
        load_calc[load_calculator]
        plan_adj[plan_adjuster]
    end

    discover_route --> analyzer
    analyze_route --> analyzer
    analyzer --> block_parser
    analyzer --> sql_extractor
    analyzer --> execute_parser
    analyzer --> nested_extractor
    analyzer --> temp_tracker
    analyzer --> antipattern
    analyzer --> load_calc
    analyzer --> plan_adj
```

### Алгоритм (этапы работы)

Двухэтапный процесс: сначала обнаружение таблиц и параметров, затем анализ нагрузки с пользовательскими размерами.

```mermaid
flowchart LR
    subgraph Stage1["Этап 1: Обнаружение"]
        A[DDL + опция БД] --> B[Парсинг тела функции]
        B --> C[Переменные и параметры]
        C --> D[Разбиение на блоки]
        D --> E[Извлечение таблиц/представлений]
        E --> F[Опционально: запрос размеров из БД]
        F --> G[Страница настроек размеров]
    end

    subgraph Stage2["Этап 2: Анализ"]
        G --> H[Параметры + размеры таблиц]
        H --> I[Подстановка переменных в блоки]
        I --> J[Очистка SQL, удаление INTO]
        J --> K[EXPLAIN по каждому блоку]
        K --> L[Применение размеров к плану]
        L --> M[Расчёт нагрузки по узлам]
        M --> N[Сумма, риск, топ-3]
    end

    Stage1 --> Stage2
```

### Логика обработки блоков

Решение по каждому блоку: учитывать в нагрузке или пропустить.

```mermaid
flowchart TD
    Start([Блок из тела функции]) --> Classify{Тип блока}
    Classify -->|DECLARE, END, RETURN, CREATE, OTHER| Skip1[Пропуск]
    Classify -->|TRUNCATE, ANALYZE, VACUUM| Skip2[Пропуск — нет EXPLAIN]
    Classify -->|SELECT/EXECUTE с INTO| CheckINTO{EXECUTE ... INTO?}
    CheckINTO -->|Да| Skip3[Пропуск — как SELECT INTO]
    CheckINTO -->|Нет| IsSQL{Исполняемый SQL?}
    Classify -->|SELECT, INSERT, UPDATE, DELETE, WITH, EXECUTE без INTO| IsSQL
    IsSQL -->|Да| Subst[Подстановка переменных]
    Subst --> Clean[Очистка: убрать INTO, комментарии]
    Clean --> Explain[EXPLAIN]
    Explain --> PlanOK{План получен?}
    PlanOK -->|Нет| Skip4[Пропуск блока]
    PlanOK -->|Да| ApplySizes[Применить размеры таблиц к плану]
    ApplySizes --> Load[Расчёт нагрузки блока]
    Load --> Append[Добавить в block_results]
    Skip1 --> Next
    Skip2 --> Next
    Skip3 --> Next
    Skip4 --> Next
    Append --> Next([Следующий блок])
```

### Архитектура (слои приложения)

Распределение по слоям: веб, задачи, ядро анализа, парсеры, расчёт.

```mermaid
flowchart TB
    subgraph Layer1["Слой 1: Веб (Flask)"]
        Routes[Маршруты /, /detailed, /detailed/discover, /detailed/analyze]
        SSE[SSE /stream, /status, /details]
        Templates[Jinja2: detailed_input, table_sizes, detailed_result]
    end

    subgraph Layer2["Слой 2: Задачи и очереди"]
        Jobs[_jobs: job_id -> payload, status, analyzer]
        Logs[_logs: job_id -> Queue строк]
        Monitor[PerformanceMonitor по job_id]
    end

    subgraph Layer3["Слой 3: Ядро анализа"]
        AnalyzerCore[DetailedGreenplumFunctionAnalyzer]
        Config[ClusterConfig: segments, ram_per_seg_gb]
        Discover[discover_tables]
        Analyze[analyze_with_user_sizes]
    end

    subgraph Layer4["Слой 4: Парсинг и извлечение"]
        BlockParser[block_parser: split_plpgsql_blocks, classify_block]
        SQLObj[SQLObjectExtractor: extract_objects]
        ExecParser[ExecuteParser: EXECUTE format/USING]
        Nested[NestedBlockExtractor]
        TempTrack[TempTableTracker]
        AntiPattern[antipattern_detector: LATERAL, CROSS JOIN, множители]
    end

    subgraph Layer5["Слой 5: Расчёт нагрузки"]
        LoadCalc[load_calculator: compute_block_load, calculate_total_load]
        PlanAdj[plan_adjuster: apply_user_sizes_to_plan]
    end

    Routes --> Jobs
    SSE --> Logs
    Templates --> Routes
    Jobs --> AnalyzerCore
    AnalyzerCore --> Discover
    AnalyzerCore --> Analyze
    Discover --> BlockParser
    Discover --> SQLObj
    Discover --> ExecParser
    Discover --> Nested
    Discover --> TempTrack
    Analyze --> AntiPattern
    Analyze --> LoadCalc
    Analyze --> PlanAdj
    Analyze --> BlockParser
    Analyze --> SQLObj
```

### Поток данных (от ввода до результата)

Как данные проходят от формы до JSON-результата и UI.

```mermaid
sequenceDiagram
    participant User
    participant Webapp
    participant Job
    participant Analyzer
    participant DB as Greenplum

    User->>Webapp: POST /detailed/discover (DDL, БД)
    Webapp->>Webapp: job_id, _jobs[job_id], _logs[job_id]
    Webapp->>Job: _run_discovery_job
    Job->>Analyzer: discover_tables(ddl)
    Analyzer->>Analyzer: block_parser, variables, SQLObjectExtractor
    opt С подключением к БД
        Analyzer->>DB: pg_class, pg_attribute (размеры таблиц)
        DB-->>Analyzer: current_rows, size_gb, avg_row_size
    end
    Analyzer-->>Job: discovered_tables, variables, blocks
    Job->>Webapp: status = tables_discovered
    Webapp->>User: redirect /discovery/result/<job_id>

    User->>Webapp: POST /detailed/analyze (job_id, params, size_*)
    Webapp->>Job: _run_analysis_job(params, user_sizes)
    Job->>Analyzer: analyze_with_user_sizes(params, user_sizes)
    loop По каждому блоку
        Analyzer->>Analyzer: _replace_variables_safe, _clean_sql_for_explain
        Analyzer->>DB: EXPLAIN (SELECT ...)
        DB-->>Analyzer: plan JSON
        Analyzer->>Analyzer: plan_adjuster.apply_user_sizes_to_plan
        Analyzer->>Analyzer: load_calculator.compute_block_load
    end
    Analyzer->>Analyzer: calculate_total_load, get_top_blocks
    Analyzer-->>Job: result (blocks_count, total_memory_gb, risk, block_details, top_blocks)
    Job->>Webapp: status = done, result
    Webapp->>User: /detailed/result/<job_id>, SSE лог, polling /status, /details
```

---

## Лицензия

Проект распространяется под лицензией [MIT](LICENSE). Автор: Dmitry Solonnikov.
