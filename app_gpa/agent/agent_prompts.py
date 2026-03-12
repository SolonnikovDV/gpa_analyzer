# -*- coding: utf-8 -*-
"""
Промпты для агента GigaChat. Редактируйте шаблоны здесь для точной настройки
поведения агента и упрощения рефакторинга. Плейсхолдеры в формате {name}.
"""

# --- Генерация SQL/функции по текстовому описанию ---
PROMPT_GENERATE_SQL = """По описанию ниже сгенерируй готовый SQL-запрос или полный DDL функции PL/pgSQL для Greenplum/PostgreSQL.
Выдай только код, без пояснений в начале и в конце. Если нужна функция — полный CREATE OR REPLACE FUNCTION ... AS $$ ... $$ LANGUAGE plpgsql.

Описание:
{description}
"""

# --- Анализ текстового описания: намерение, недостающие части, достаточность контекста ---
PROMPT_ANALYZE_DESCRIPTION = """Проанализируй текст пользователя и определи:
1) Намерение: пользователь просит "создать функцию в схеме" (и описание того, что делает функция) или "составить запрос" (и описание того, что делает запрос)?
   Верни одно из: "function" или "query".
2) Для функции определи недостающие части (если из текста понятно — укажи, иначе отметь как "не указано"):
   - что возвращает функция (RETURNS тип);
   - параметры сигнатуры (имя и тип);
   - источники данных (таблицы/представления с атрибутами и типами, если упомянуты);
   - датафлоу: откуда берутся данные;
   - результат: куда положить результат;
3) Оцени достаточность контекста бизнес-логики для однозначной генерации. Достаточно ли данных для понимания?
4) Если контекста недостаточно — сформулируй краткое предупреждение (1-2 предложения) о том, что генерация может быть неточной и что стоит уточнить.

Верни только один JSON-объект в формате (без markdown и пояснений):
{{"intent": "function" или "query", "return_type": "текст или null", "signature_params": ["имя тип", ...], "data_sources": ["schema.table или описание"], "dataflow": "кратко", "result_target": "кратко", "context_sufficient": true/false, "warning": "предупреждение или null"}}

Текст пользователя:
{description}
"""

# --- Синтез плана запроса (без БД) ---
PROMPT_SYNTHESIZE_PLAN = """По SQL для Greenplum/PostgreSQL сформируй план выполнения в формате JSON, как от EXPLAIN (FORMAT JSON).
Верни только один JSON-объект без markdown и пояснений, в таком виде:
{{"Plan": {{ "Node Type": "тип_узла", "Plan Rows": число, "Plan Width": 100, "Relation Name": "имя_таблицы" или null, "Plans": [] }}}}

Типы узлов используй: Seq Scan, Index Scan, Hash Join, Nested Loop, Sort, Hash Aggregate, ModifyTable, Append, и т.п.
Для каждого скана таблицы укажи Relation Name и Plan Rows (оценка строк). Если даны размеры таблиц — используй их для Plan Rows.

КРИТИЧНО: Все тяжёлые паттерны оценивай В КОНТЕКСТЕ конкретного запроса. Рост нагрузки при скейле данных = размеры таблиц, заданные пользователем. Plan Rows должен масштабироваться с этими размерами.

ВАЖНО — сложность LATERAL подзапросов:
LEFT JOIN LATERAL (SELECT ... FROM view WHERE ... ORDER BY ... LIMIT 1) — зависимый подзапрос, выполняется для КАЖДОЙ строки внешней таблицы.
На скейле данных это создаёт N+1 нагрузку: подзапрос может вызываться миллиарды раз.
При моделировании плана: Plan Rows для LATERAL-узла = строки_внешней_таблицы × оценка_строк_в_подзапросе (или умножь на множитель сложности).
Учитывай: LATERAL с ORDER BY + LIMIT 1 — высокий риск на больших объёмах, может «свалить» БД или уйти в долгий расчёт.

ВАЖНО — сложность CROSS JOIN:
CROSS JOIN (или FROM a, b без условия) — декартово произведение: выходных строк = строки_таблицы_A × строки_таблицы_B.
На скейле с пользовательскими размерами: если A = 5 млрд строк, B = 1 млн — Plan Rows для узла Nested Loop/Join = 5e15.
Используй указанные пользователем размеры таблиц: Plan Rows = rows_A × rows_B для CROSS JOIN.

Другие тяжёлые паттерны (моделируй на скейле с учётом размеров таблиц):
• Коррелированный подзапрос (WHERE x IN (SELECT ... WHERE outer.col = inner.col)) — выполняется для каждой строки внешней таблицы. Plan Rows ≈ строки_внешней × строки_внутренней.
• Self-join (таблица соединена сама с собой) — Plan Rows может быть rows² при плохом селекторе; учитывай размер таблицы.
• UNION без ALL — требует Sort + Unique для дедупликации; Plan Rows = сумма всех веток, но Sort обрабатывает все строки.
• Recursive CTE — планировщик часто завышает оценки; при глубокой рекурсии или широком fan-out Plan Rows может взрываться.
• ORDER BY без LIMIT на большом результате — полная сортировка всех строк; Plan Rows = размер входа, Sort обрабатывает всё.
• NOT IN (subquery) — часто выполняется как вложенный SubPlan, не anti-join; учитывай размер подзапроса × внешней таблицы.
• Hash Join при низкой кардинальности ключа — может не влезть в work_mem, spill на диск; при больших размерах таблиц учитывай риск.
• SELECT DISTINCT — полная сортировка или HashAggregate по всем входным строкам; Sort/HashAggregate обрабатывает весь вход (Plan Rows входа = размер таблицы). При низкой кардинальности выход мал, но стоимость = O(n) или O(n log n).
• Функции в условиях (non-SARGable): date_trunc(ts)=..., LOWER(col)=... — блокируют индекс и pushdown; Plan Rows = полный скан таблицы (используй размер из tables_desc).
• LIMIT в запросе — планировщик может выбрать Nested Loop «на мало строк», но фактически сканировать миллионы; учитывай реальные размеры таблиц.
• ORDER BY + LIMIT — planner может выбрать full index scan в неправильном направлении; при больших таблицах Plan Rows = размер скана.
• Data skew — неравномерное распределение по ключам; часть сегментов/партиций обрабатывает гораздо больше строк; умножь оценку на коэффициент skew.
• Большие IN (...) или много OR в WHERE — ухудшают производительность; Plan Rows может быть занижен, учитывай размер подзапроса/списка.
• DISTINCT ON в подзапросе — PostgreSQL обрабатывает весь подзапрос до фильтрации; Plan Rows входа = размер подзапроса.
• Поздняя фильтрация — WHERE после JOIN вместо до; обрабатывается лишний объём; фильтруй в CTE до join, используй размеры после фильтра.

ВРЕМЕННЫЕ ТАБЛИЦЫ — определяй сам и выстраивай наследование:
• CREATE TEMP TABLE x AS SELECT ... FROM a JOIN b — x наследует от a и b; при нескольких родителях (JOIN, UNION) бери размер САМОГО БОЛЬШОГО.
• INSERT INTO tmp_agg SELECT ... FROM tmp_sales_stage — tmp_agg наследует от tmp_sales_stage; tmp_sales_stage наследует от своих источников. Цепочка может быть опосредованной: tmp_agg → tmp_sales_stage → v_stg_sales_daily. Plan Rows для временной таблицы = размер крупнейшего родителя в tables_desc (рекурсивно по цепочке).
• Для Plan Rows временной таблицы: найди её источники в SQL (FROM, JOIN, UNION), определи базовые таблицы/представления в цепочке, возьми max(размеры из tables_desc).

ЕСЛИ ПАРСЕР НЕ СМОГ РАЗОБРАТЬ SQL (ошибка синтаксиса, артефакты EXECUTE FORMAT, лишние кавычки в идентификаторах) — интерпретируй запрос по смыслу: извлеки имена таблиц из текста вручную (в т.ч. schema.table, партиции вида table_YYYY_MM), сопоставь с базовыми таблицами в tables_desc (партиция table_2024_01 → базовая table), построй план на основе понимания намерения запроса.

ЕСЛИ В SQL ОСТАЛИСЬ НЕПОДСТАВЛЕННЫЕ ПЕРЕМЕННЫЕ ИЛИ ПАРАМЕТРЫ (NULL вместо даты, p_start_dt, p_end_dt и т.п.) — используй значения из params_and_vars для интерпретации: подставь их мысленно при оценке плана (например, BETWEEN p_start_dt AND p_end_dt при p_start_dt='2024-01-01', p_end_dt=current_date — полный скан за период; date-параметры не сужают выборку существенно при оценке Plan Rows по размерам таблиц).
{params_and_vars}
{tables_desc}

SQL:
{query}
"""

# --- Извлечение блоков и объектов из DDL/SQL (чистый агентский режим) ---
PROMPT_BLOCKS_AND_OBJECTS = """Перед тобой может быть: PL/pgSQL функция (CREATE FUNCTION ... AS $function$), один SQL-запрос, или скрипт (несколько DDL/DML: DROP TABLE, CREATE TABLE, INSERT, SELECT и т.д.). Определи тип ввода сам и извлеки блоки и объекты соответственно.

По тексту определи:

1) Исполняемые SQL-блоки — КАЖДЫЙ отдельно по порядку появления в тексте.
   Не объединяй несколько INSERT/UPDATE/DELETE в один блок. Каждый TRUNCATE, INSERT, UPDATE, DELETE, EXECUTE — отдельный блок.
   Типы: SELECT, INSERT, UPDATE, DELETE, TRUNCATE, EXECUTE. Игнорируй: SELECT INTO переменную, EXECUTE INTO, l_log :=, srv_*, GET DIAGNOSTICS.

2) ОБЪЕКТЫ (источники данных — таблицы и представления). ОБЯЗАТЕЛЬНО найди ВСЕ:
   - INSERT INTO schema.table — целевая таблица (schema.table) — объект.
   - SELECT ... FROM schema.table, JOIN schema.view — оба объекты.
   - UPDATE schema.table ... FROM schema.view — оба объекты.
   - LATERAL подзапросы: LEFT JOIN LATERAL (SELECT ... FROM schema.view ft ...) ft ON true — schema.view внутри LATERAL тоже объект! Не пропускай.
   - Подзапросы: в любом FROM, включая вложенные и LATERAL — каждая schema.table / schema.view в FROM — объект.
   - TRUNCATE schema.table, DELETE FROM schema.table — schema.table объект.
   ВАЖНО: НЕ путать с атрибутами! alias.column (m.dtoptndate, ft.seg_client_cx_segment_cd) — это колонки, НЕ таблицы. В objects только schema.table или schema.view.
   НЕ включать: типы данных (tp_log_instance, tp_* и т.п.), srv_*, sq_*, sequence — это не таблицы/представления.
   Имена вида v_stg_*, v_* в контексте FROM/JOIN — это представления (views), не переменные. Включай их в objects.
   Временные таблицы: CREATE TEMP TABLE <name> — без схемы. INSERT INTO <temp> ... FROM <source> — оба объекты.
   НЕ путать: SELECT col INTO variable — присваивание переменной, не таблица.

3) Параметры функции: только если это PL/pgSQL — имена из сигнатуры (CREATE FUNCTION name(param1 type, param2 type)). Для скрипта или одного запроса — [].

4) Переменные: только если это PL/pgSQL — объявляются в DECLARE. Для скрипта или одного запроса — [].

Верни только один JSON-объект:
{{"blocks": [{{"type": "SELECT", "sql": "..."}}, ...], "objects": ["schema.table", "schema.view", ...], "function_params": ["param1", "param2"], "variables": ["var1", "var2"]}}
Типы блоков: SELECT, INSERT, UPDATE, DELETE, TRUNCATE, EXECUTE, DROP_TABLE, CREATE_TABLE (для скриптов). Порядок — строго по появлению в тексте. Каждый оператор — отдельный элемент в blocks.
Текст:
{text}
"""

# --- Часть текста (для разбиения на чанки) ---
PROMPT_BLOCKS_AND_OBJECTS_CHUNK = """Это ЧАСТЬ {part_num} из {total_parts} текста. Тип может быть: PL/pgSQL функция, SQL-скрипт (DDL/DML) или запрос. Извлеки блоки и объекты ТОЛЬКО из этой части.

Правила: каждый DROP TABLE, CREATE TABLE, TRUNCATE, INSERT, UPDATE, DELETE, SELECT, EXECUTE — отдельный блок. objects — все schema.table/schema.view. function_params и variables — только если в части есть DECLARE/параметры функции, иначе [].

Верни JSON: {{"blocks": [{{"type": "...", "sql": "..."}}, ...], "objects": ["schema.table", ...], "function_params": [], "variables": []}}

Часть {part_num}:
{text}
"""

# --- Список объектов (таблицы/представления) из SQL/функции ---
PROMPT_OBJECTS_FROM_SQL = """По тексту PL/pgSQL функции или SQL запроса выпиши полный список ВСЕХ таблиц и представлений (источников данных).

Правила:
- INSERT INTO schema.table — целевая таблица schema.table — объект.
- SELECT/UPDATE/DELETE: FROM schema.table, JOIN schema.view — оба объекты.
- LATERAL подзапросы: LEFT JOIN LATERAL (SELECT ... FROM schema.view ft ...) — schema.view внутри LATERAL тоже объект! Обязательно включи.
- Подзапросы: каждая schema.table или schema.view в любом FROM (включая вложенные и LATERAL) — объект.
- TRUNCATE schema.table, DELETE FROM schema.table — schema.table объект.
- НЕ путать с атрибутами! alias.column (m.dtoptndate, ft.seg_client_cx_segment_cd) — колонки, НЕ таблицы.
- Имена v_stg_*, v_* в контексте FROM/JOIN — это представления (views), включай в objects.
- Временные таблицы: CREATE TEMP TABLE <name> — без схемы. INSERT INTO <temp> ... FROM <source> — оба объекты.
- НЕ путать: SELECT col INTO variable — присваивание, не таблица. Игнорируй srv_* и log.
Верни только JSON-массив строк: ["schema.table", "schema.view", ...]. Если schema не указан — public.
Текст:
{text}
"""

# --- Недостающие объекты для запроса DDL ---
PROMPT_MISSING_OBJECTS = """В тексте PL/pgSQL или SQL перечислены объекты (таблицы/представления). Мы уже имеем DDL или статистику по объектам: {found_objects}.
Определи, какие ещё объекты из текста могут потребовать DDL (например представления или таблицы, которых нет в списке). Верни только JSON-массив строк с полными именами schema.name, например ["schema.v1", "schema.t2"]. Если недостающих нет — верни [].
Текст:
{text}
"""


def get_prompt(name: str, **kwargs) -> str:
    """Возвращает промпт по имени с подставленными значениями. Имена: generate_sql, analyze_description, synthesize_plan, blocks_and_objects, objects_from_sql, missing_objects."""
    prompts = {
        "generate_sql": PROMPT_GENERATE_SQL,
        "analyze_description": PROMPT_ANALYZE_DESCRIPTION,
        "synthesize_plan": PROMPT_SYNTHESIZE_PLAN,
        "blocks_and_objects": PROMPT_BLOCKS_AND_OBJECTS,
        "blocks_and_objects_chunk": PROMPT_BLOCKS_AND_OBJECTS_CHUNK,
        "objects_from_sql": PROMPT_OBJECTS_FROM_SQL,
        "missing_objects": PROMPT_MISSING_OBJECTS,
    }
    tpl = prompts.get(name)
    if not tpl:
        raise ValueError(f"Unknown prompt: {name}")
    return tpl.format(**kwargs)
