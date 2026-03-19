from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal


StackType = Literal["greenplum", "spark", "pyspark"]
ScenarioType = Literal["agent", "hybrid", "logic"]


@dataclass(frozen=True)
class RuntimeCapabilities:
    requires_connection_before_input: bool = False
    supports_catalog_metadata: bool = False
    supports_completion: bool = False
    supports_quick_fixes: bool = False
    supports_agent: bool = True
    supports_native_analysis: bool = False


@dataclass(frozen=True)
class ConnectionField:
    name: str
    label: str
    kind: str = "text"
    required: bool = False
    placeholder: str = ""


@dataclass(frozen=True)
class RuntimeDescriptor:
    stack: StackType
    scenario: ScenarioType
    source_label: str
    editor_mode: str
    connection_label: str
    capabilities: RuntimeCapabilities
    connection_fields: List[ConnectionField] = field(default_factory=list)
    cluster_fields: List[ConnectionField] = field(default_factory=list)
    ui: Dict[str, Any] = field(default_factory=dict)
    optional: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["capabilities"] = asdict(self.capabilities)
        data["connection_fields"] = [asdict(item) for item in self.connection_fields]
        data["cluster_fields"] = [asdict(item) for item in self.cluster_fields]
        data["ui"] = dict(self.ui)
        return data


def normalize_stack(value: str | None) -> StackType:
    candidate = str(value or "").strip().lower()
    if candidate in {"", "greenplum", "postgres", "postgresql", "gp"}:
        return "greenplum"
    if candidate in {"spark", "spark-sql", "sparksql"}:
        return "spark"
    if candidate in {"pyspark", "py-spark"}:
        return "pyspark"
    return "greenplum"


def normalize_scenario(value: str | None) -> ScenarioType:
    candidate = str(value or "").strip().lower()
    if candidate in {"agent", "pure-agent", "pure_agent"}:
        return "agent"
    if candidate in {"hybrid"}:
        return "hybrid"
    if candidate in {"analytics", "logic", "analysis"}:
        return "logic"
    return "logic"


def get_supported_stacks() -> List[Dict[str, Any]]:
    return [
        {"id": "greenplum", "label": "GreenPlum", "optional": False},
        {"id": "spark", "label": "Spark", "optional": False},
        {"id": "pyspark", "label": "PySpark", "optional": False},
    ]


def get_supported_scenarios() -> List[Dict[str, Any]]:
    return [
        {"id": "agent", "label": "Агент"},
        {"id": "hybrid", "label": "Гибрид"},
        {"id": "logic", "label": "Логика"},
    ]


def get_runtime_descriptor(stack: str | None, scenario: str | None) -> RuntimeDescriptor:
    runtime_stack = normalize_stack(stack)
    runtime_scenario = normalize_scenario(scenario)

    if runtime_stack == "spark":
        return RuntimeDescriptor(
            stack="spark",
            scenario=runtime_scenario,
            source_label="Spark SQL",
            editor_mode="text/x-sql",
            connection_label="Подключение к Spark",
            capabilities=RuntimeCapabilities(
                requires_connection_before_input=runtime_scenario in {"hybrid", "logic"},
                supports_catalog_metadata=runtime_scenario in {"hybrid", "logic"},
                supports_completion=True,
                supports_quick_fixes=True,
                supports_agent=True,
                supports_native_analysis=runtime_scenario in {"hybrid", "logic"},
            ),
            connection_fields=[
                ConnectionField("master_url", "Master URL", required=runtime_scenario in {"hybrid", "logic"}, placeholder="spark://host:7077"),
                ConnectionField("catalog", "Catalog / Metastore", placeholder="hive_metastore"),
                ConnectionField("namespace", "Namespace / Database", placeholder="default"),
                ConnectionField("user", "User"),
                ConnectionField("password", "Password", kind="password"),
            ],
            cluster_fields=[
                ConnectionField("executor_instances", "Executor instances", kind="number", placeholder="4"),
                ConnectionField("executor_cores", "Executor cores", kind="number", placeholder="4"),
                ConnectionField("executor_memory", "Executor memory", placeholder="8g"),
            ],
            ui={
                "stack_label": "Spark",
                "status_default": "Проверка Spark SQL",
                "status_checking": "Проверяем Spark SQL...",
                "status_valid": "Spark SQL: базовая проверка пройдена",
                "status_invalid": "Проверьте синтаксис Spark SQL",
                "status_warning": "Есть предупреждения Spark SQL",
                "source_field_label": "Spark SQL",
                "source_placeholder": "Вставьте Spark SQL запрос или скрипт",
                "source_help": "Можно вставить Spark SQL запрос, CTE-скрипт или DDL.",
                "cluster_title": "Настройки рантайма Spark",
                "cluster_caption": "Укажите параметры executors и при необходимости добавьте metadata/profile snapshot для более точной оценки. JSON можно вставить или загрузить из файла.",
                "connection_title": "Подключение к Spark",
                "connection_caption": "Для сценариев с рантаймом можно подтвердить доступ к Spark до ввода кода.",
                "connection_missing": "Для проверки Spark заполните хотя бы Master URL.",
                "connection_checking": "Проверяем подключение к Spark...",
                "connection_success": "Параметры Spark runtime приняты. Редактор разблокирован.",
                "connection_required": "Для сценариев со Spark runtime сначала подтвердите подключение.",
                "gate_title": "Сначала подключите Spark",
                "gate_hint": "Откройте окно подключения Spark и подтвердите параметры рантайма.",
                "sidebar_subtitle": "Spark SQL, агент, рантайм",
                "cluster_nav_label": "Настройки Spark",
                "scenario_help_agent": "Агент: можно анализировать Spark SQL без рантайма или через агента.",
                "scenario_help_hybrid": "Гибрид: Spark runtime и агент используются вместе.",
                "scenario_help_logic": "Логика: используется Spark runtime без генерации через агента.",
            },
        )

    if runtime_stack == "pyspark":
        return RuntimeDescriptor(
            stack="pyspark",
            scenario=runtime_scenario,
            source_label="PySpark code",
            editor_mode="text/x-python",
            connection_label="Подключение к PySpark runtime",
            capabilities=RuntimeCapabilities(
                requires_connection_before_input=runtime_scenario in {"hybrid", "logic"},
                supports_catalog_metadata=runtime_scenario in {"hybrid", "logic"},
                supports_completion=True,
                supports_quick_fixes=True,
                supports_agent=True,
                supports_native_analysis=False,
            ),
            connection_fields=[
                ConnectionField("master_url", "Master URL", required=runtime_scenario in {"hybrid", "logic"}, placeholder="spark://host:7077"),
                ConnectionField("session_name", "Session name", placeholder="gpa-pyspark"),
                ConnectionField("user", "User"),
                ConnectionField("password", "Password", kind="password"),
            ],
            cluster_fields=[
                ConnectionField("executor_instances", "Executor instances", kind="number", placeholder="4"),
                ConnectionField("executor_memory", "Executor memory", placeholder="8g"),
            ],
            ui={
                "stack_label": "PySpark",
                "status_default": "Проверка PySpark кода",
                "status_checking": "Проверяем PySpark код...",
                "status_valid": "PySpark: базовая проверка пройдена",
                "status_invalid": "Проверьте PySpark код",
                "status_warning": "Есть предупреждения PySpark",
                "source_field_label": "PySpark code",
                "source_placeholder": "Вставьте PySpark код, DataFrame pipeline или spark.sql(...)",
                "source_help": "Можно вставить PySpark код, DataFrame API или spark.sql(...) вызовы.",
                "cluster_title": "Настройки рантайма PySpark",
                "cluster_caption": "Укажите параметры сессии и при необходимости добавьте metadata/profile snapshot для более точной оценки. JSON можно вставить или загрузить из файла.",
                "connection_title": "Подключение к PySpark runtime",
                "connection_caption": "Для сценариев с рантаймом можно подтвердить параметры PySpark до ввода кода.",
                "connection_missing": "Для проверки PySpark заполните хотя бы Master URL.",
                "connection_checking": "Проверяем параметры PySpark runtime...",
                "connection_success": "Параметры PySpark runtime приняты. Редактор разблокирован.",
                "connection_required": "Для сценариев с PySpark runtime сначала подтвердите параметры подключения.",
                "gate_title": "Сначала подключите PySpark runtime",
                "gate_hint": "Откройте окно подключения PySpark и подтвердите параметры рантайма.",
                "sidebar_subtitle": "PySpark, агент, рантайм",
                "cluster_nav_label": "Настройки PySpark",
                "scenario_help_agent": "Агент: можно анализировать PySpark код без рантайма или через агента.",
                "scenario_help_hybrid": "Гибрид: PySpark runtime и агент используются вместе.",
                "scenario_help_logic": "Логика: используется PySpark runtime без генерации через агента.",
            },
            optional=False,
        )

    return RuntimeDescriptor(
        stack="greenplum",
        scenario=runtime_scenario,
        source_label="SQL / DDL",
        editor_mode="text/x-pgsql",
        connection_label="Подключение к GreenPlum",
        capabilities=RuntimeCapabilities(
            requires_connection_before_input=runtime_scenario in {"hybrid", "logic"},
            supports_catalog_metadata=runtime_scenario in {"hybrid", "logic"},
            supports_completion=True,
            supports_quick_fixes=True,
            supports_agent=True,
            supports_native_analysis=True,
        ),
        connection_fields=[
            ConnectionField("stand_type", "Stand", required=True, placeholder="PROM"),
            ConnectionField("host", "Host"),
            ConnectionField("port", "Port", kind="number", placeholder="5432"),
            ConnectionField("dbname", "Database"),
            ConnectionField("user", "User", required=True),
            ConnectionField("password", "Password", kind="password", required=True),
        ],
        cluster_fields=[
            ConnectionField("segments", "Segments", kind="number", placeholder="120"),
            ConnectionField("ram_per_seg_gb", "RAM per segment (GB)", kind="number", placeholder="153.6"),
        ],
        ui={
            "stack_label": "GreenPlum",
            "status_default": "Проверка синтаксиса PostgreSQL",
            "status_checking": "Проверяем синтаксис PostgreSQL...",
            "status_valid": "PostgreSQL: синтаксис корректен",
            "status_invalid": "Ошибка синтаксиса PostgreSQL",
            "status_warning": "Есть предупреждения SQL",
            "source_field_label": "SQL или DDL",
            "source_placeholder": "Вставьте полный текст запроса или функции",
            "source_help": "Можно вставить функцию, одиночный запрос или SQL-скрипт.",
            "cluster_title": "Настройки кластера GreenPlum",
            "cluster_caption": "В этой view остаются только параметры кластера. Подключение к БД запрашивается по сценарию при расчёте.",
            "connection_title": "Подключение к GreenPlum",
            "connection_caption": "Этот modal доступен только в режимах, где приложение может работать через БД. Логин и пароль нужны для проверки подключения перед переходом к следующему шагу.",
            "connection_missing": "Для проверки подключения заполните логин и пароль GreenPlum.",
            "connection_checking": "Проверяем подключение к GreenPlum...",
            "connection_success": "Подключение подтверждено. SQL-окна разблокированы.",
            "connection_required": "Для сценариев с БД сначала подтвердите подключение к GreenPlum.",
            "gate_title": "Сначала подключите GreenPlum",
            "gate_hint": "Откройте окно подключения GreenPlum, проверьте логин и пароль, затем нажмите «Проверить и применить».",
            "sidebar_subtitle": "SQL, агент, кластер",
            "cluster_nav_label": "Настройки GreenPlum",
            "scenario_help_agent": "Агент: до расчёта можно переключаться между генерацией по описанию и своим скриптом.",
            "scenario_help_hybrid": "Гибрид: по нажатию расчёта запрашиваются API-профиль и подключение к БД. Генерации по описанию нет.",
            "scenario_help_logic": "Аналитика: по нажатию расчёта запрашивается подключение к БД.",
        },
    )
