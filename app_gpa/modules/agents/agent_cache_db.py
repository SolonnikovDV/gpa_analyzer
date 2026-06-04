# -*- coding: utf-8 -*-
"""
Кэш агента на SQLite: сохранение состояний, проверка валидности, переиспользование.
Опционально: sqlite-vec для семантического кэша (похожие запросы → переиспользование ответа, экономия токенов).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.paths import AGENT_CACHE_DIR, AGENT_PROFILES_PATH, ensure_runtime_dirs

ensure_runtime_dirs()
_LEGACY_CACHE_DIR = Path(__file__).resolve().parent
_CACHE_DIR = AGENT_CACHE_DIR
_DB_PATH = _CACHE_DIR / ".agent_cache.db"
_BASELINE_DB_PATH = _CACHE_DIR / ".agent_cache.baseline.db"
_BASELINE_JSON_PATH = _CACHE_DIR / ".agent_cache.baseline.json"
_BASELINE_CONFIG_PATH = _CACHE_DIR / ".agent_baseline_config.json"
_AGENT_PROFILES_PATH = AGENT_PROFILES_PATH


def _migrate_legacy_cache_dir() -> None:
    if _LEGACY_CACHE_DIR.resolve() == _CACHE_DIR.resolve():
        return
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for name in (
        ".agent_cache.db",
        ".agent_cache.baseline.db",
        ".agent_cache.json",
        ".agent_cache.baseline.json",
        ".agent_baseline_config.json",
    ):
        legacy = _LEGACY_CACHE_DIR / name
        target = _CACHE_DIR / name
        if legacy.exists() and not target.exists():
            shutil.copy2(legacy, target)


_migrate_legacy_cache_dir()

# Базовое состояние, зашитое в ядре — настройки не опускаются ниже этого уровня
_CORE_BASELINE = {
    "profiles": [],
    "config": {
        "GIGACHAT_VERIFY_SSL_CERTS": "false",
    },
}
_VEC_TABLE = "agent_vec_cache"
_LOCK = threading.RLock()

# TTL по умолчанию (дней): после этого запись считается устаревшей
DEFAULT_TTL_DAYS = 30
# Порог косинусной близости для переиспользования по вектору (0..1, выше = строже)
DEFAULT_SIMILARITY_THRESHOLD = 0.97


def _normalize(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.strip().split())


def _key_hash(prefix: str, key_data: str) -> str:
    norm = _normalize(key_data)
    return hashlib.sha256(f"{prefix}:{norm}".encode("utf-8")).hexdigest()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agent_exact_cache (
            key_hash TEXT PRIMARY KEY,
            prefix TEXT NOT NULL,
            response TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_exact_prefix ON agent_exact_cache(prefix);
        CREATE INDEX IF NOT EXISTS idx_exact_created ON agent_exact_cache(created_at);

        CREATE TABLE IF NOT EXISTS agent_state_cache (
            state_key TEXT PRIMARY KEY,
            state_data TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_state_created ON agent_state_cache(created_at);

        CREATE TABLE IF NOT EXISTS plan_cache (
            query_hash TEXT NOT NULL,
            sizes_hash TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (query_hash, sizes_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_plan_created ON plan_cache(created_at);

        CREATE TABLE IF NOT EXISTS token_usage_totals (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            sessions INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO token_usage_totals (id, prompt_tokens, completion_tokens, total_tokens) VALUES (1, 0, 0, 0);

        CREATE TABLE IF NOT EXISTS token_usage_by_provider (
            provider TEXT PRIMARY KEY,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            sessions INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO token_usage_by_provider (provider, prompt_tokens, completion_tokens, total_tokens, sessions)
            VALUES ('gigachat', 0, 0, 0, 0);
        INSERT OR IGNORE INTO token_usage_by_provider (provider, prompt_tokens, completion_tokens, total_tokens, sessions)
            VALUES ('deepseek', 0, 0, 0, 0);
    """)
    # Миграция: добавить sessions если колонки нет
    try:
        cur = conn.execute("PRAGMA table_info(token_usage_totals)")
        cols = [r[1] for r in cur.fetchall()]
        if "sessions" not in cols:
            conn.execute("ALTER TABLE token_usage_totals ADD COLUMN sessions INTEGER NOT NULL DEFAULT 0")
            conn.execute("UPDATE token_usage_totals SET sessions = 0 WHERE id = 1")
            conn.commit()
    except Exception:
        pass


def add_token_usage_for_provider(
    provider: str,
    prompt_delta: int,
    completion_delta: int,
    total_delta: int,
    sessions_delta: int = 0,
) -> None:
    if not provider:
        return
    if prompt_delta == 0 and completion_delta == 0 and total_delta == 0 and sessions_delta == 0:
        return
    with _LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            conn.execute(
                """INSERT INTO token_usage_by_provider (provider, prompt_tokens, completion_tokens, total_tokens, sessions)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(provider) DO UPDATE SET
                   prompt_tokens = prompt_tokens + excluded.prompt_tokens,
                   completion_tokens = completion_tokens + excluded.completion_tokens,
                   total_tokens = total_tokens + excluded.total_tokens,
                   sessions = sessions + excluded.sessions""",
                (provider, prompt_delta, completion_delta, total_delta, sessions_delta),
            )
            conn.commit()
        finally:
            conn.close()


def get_token_usage_for_provider(provider: str) -> Optional[Dict[str, int]]:
    if not provider:
        return None
    with _LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            row = conn.execute(
                "SELECT prompt_tokens, completion_tokens, total_tokens, sessions FROM token_usage_by_provider WHERE provider = ?",
                (provider,),
            ).fetchone()
            if not row:
                return None
            return {
                "prompt_tokens": row[0] or 0,
                "completion_tokens": row[1] or 0,
                "total_tokens": row[2] or 0,
                "sessions": row[3] if len(row) > 3 else 0,
            }
        finally:
            conn.close()


def add_token_usage(prompt_delta: int, completion_delta: int, total_delta: int, sessions_delta: int = 0) -> None:
    """Увеличивает накопленные счётчики токенов и сессий (для плашки «использовано» после перезапуска)."""
    if prompt_delta == 0 and completion_delta == 0 and total_delta == 0 and sessions_delta == 0:
        return
    with _LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            conn.execute(
                """UPDATE token_usage_totals SET
                   prompt_tokens = prompt_tokens + ?,
                   completion_tokens = completion_tokens + ?,
                   total_tokens = total_tokens + ?,
                   sessions = sessions + ?
                   WHERE id = 1""",
                (prompt_delta, completion_delta, total_delta, sessions_delta),
            )
            conn.commit()
        finally:
            conn.close()


def get_token_usage_totals() -> Optional[Dict[str, int]]:
    """Возвращает накопленные за всё время prompt_tokens, completion_tokens, total_tokens, sessions из БД."""
    with _LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            row = conn.execute(
                "SELECT prompt_tokens, completion_tokens, total_tokens, sessions FROM token_usage_totals WHERE id = 1"
            ).fetchone()
            if not row:
                return None
            return {
                "prompt_tokens": row[0] or 0,
                "completion_tokens": row[1] or 0,
                "total_tokens": row[2] or 0,
                "sessions": row[3] if len(row) > 3 else 0,
            }
        except sqlite3.OperationalError:
            row = conn.execute(
                "SELECT prompt_tokens, completion_tokens, total_tokens FROM token_usage_totals WHERE id = 1"
            ).fetchone()
            if not row:
                return None
            return {
                "prompt_tokens": row[0] or 0,
                "completion_tokens": row[1] or 0,
                "total_tokens": row[2] or 0,
                "sessions": 0,
            }
        finally:
            conn.close()


def _vec_available() -> bool:
    try:
        import sqlite_vec  # noqa: F401
        return True
    except ImportError:
        return False


def vec_available() -> bool:
    """Публичная проверка: установлен ли sqlite-vec для семантического кэша."""
    return _vec_available()


def _init_vec(conn: sqlite3.Connection) -> bool:
    if not _vec_available():
        return False
    try:
        conn.enable_load_extension(True)
        import sqlite_vec
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {_VEC_TABLE} (
                key_hash TEXT PRIMARY KEY,
                prefix TEXT NOT NULL,
                response TEXT NOT NULL,
                embedding BLOB,
                created_at TEXT NOT NULL
            )
        """)
        return True
    except Exception:
        return False


def get(prefix: str, key_data: str, ttl_days: Optional[int] = DEFAULT_TTL_DAYS) -> Optional[str]:
    """
    Точное совпадение: key_hash = sha256(prefix + normalize(key_data)).
    Проверка валидности: совпадение хеша (повторный расчёт от текущего key_data).
    При ttl_days: запись старше не возвращается.
    """
    key_hash = _key_hash(prefix, key_data)
    with _LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            row = conn.execute(
                "SELECT response, created_at FROM agent_exact_cache WHERE key_hash = ?",
                (key_hash,),
            ).fetchone()
            if not row:
                return None
            response, created_at = row[0], row[1]
            if ttl_days is not None and created_at:
                try:
                    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - created) > timedelta(days=ttl_days):
                        conn.execute("DELETE FROM agent_exact_cache WHERE key_hash = ?", (key_hash,))
                        conn.commit()
                        return None
                except Exception:
                    pass
            return response
        finally:
            conn.close()


def set(prefix: str, key_data: str, response: str) -> None:
    """Сохранить ответ в точный кэш."""
    key_hash = _key_hash(prefix, key_data)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with _LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            conn.execute(
                "INSERT OR REPLACE INTO agent_exact_cache (key_hash, prefix, response, created_at) VALUES (?, ?, ?, ?)",
                (key_hash, prefix, response, now),
            )
            conn.commit()
        finally:
            conn.close()


def get_state(state_key: str, ttl_days: Optional[int] = DEFAULT_TTL_DAYS) -> Optional[Dict[str, Any]]:
    """Получить сохранённое состояние (например, результат discovery) с проверкой TTL."""
    with _LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            row = conn.execute(
                "SELECT state_data, created_at FROM agent_state_cache WHERE state_key = ?",
                (state_key,),
            ).fetchone()
            if not row:
                return None
            data, created_at = row[0], row[1]
            if ttl_days is not None and created_at:
                try:
                    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - created) > timedelta(days=ttl_days):
                        conn.execute("DELETE FROM agent_state_cache WHERE state_key = ?", (state_key,))
                        conn.commit()
                        return None
                except Exception:
                    pass
            try:
                return json.loads(data)
            except Exception:
                return None
        finally:
            conn.close()


def set_state(state_key: str, state_data: Dict[str, Any]) -> None:
    """Сохранить состояние (discovery/analysis) для переиспользования."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with _LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            conn.execute(
                "INSERT OR REPLACE INTO agent_state_cache (state_key, state_data, created_at) VALUES (?, ?, ?)",
                (state_key, json.dumps(state_data, ensure_ascii=False), now),
            )
            conn.commit()
        finally:
            conn.close()


def get_similar(
    prefix: str,
    embedding: List[float],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ttl_days: Optional[int] = DEFAULT_TTL_DAYS,
) -> Optional[Tuple[str, float]]:
    """
    Поиск по вектору (если доступен sqlite-vec). Возвращает (response, similarity) или None.
    Используется для переиспользования ответа при похожем запросе (экономия токенов).
    """
    if not _vec_available() or not embedding:
        return None
    with _LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            if not _init_vec(conn):
                return None
            import sqlite_vec
            blob = sqlite_vec.serialize_float32(embedding)
            # KNN: vec_distance_cosine, меньше = ближе; similarity = 1 - distance
            rows = conn.execute(f"""
                SELECT key_hash, response, vec_distance_cosine(embedding, ?) AS dist
                FROM {_VEC_TABLE}
                WHERE prefix = ? AND embedding IS NOT NULL
                ORDER BY dist LIMIT 1
            """, (blob, prefix)).fetchall()
            if not rows:
                return None
            row = rows[0]
            dist = row[2]
            sim = 1.0 - dist if dist is not None else 0.0
            if sim < threshold:
                return None
            # TTL check
            created_row = conn.execute(
                f"SELECT created_at FROM {_VEC_TABLE} WHERE key_hash = ?",
                (row[0],),
            ).fetchone()
            if ttl_days and created_row:
                try:
                    created = datetime.fromisoformat(created_row[0].replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - created) > timedelta(days=ttl_days):
                        return None
                except Exception:
                    pass
            return (row[1], sim)
        except Exception:
            return None
        finally:
            conn.close()


def set_vector(prefix: str, key_data: str, embedding: List[float], response: str) -> None:
    """Сохранить ответ в векторный кэш (для семантического переиспользования)."""
    if not _vec_available() or not embedding:
        return
    key_hash = _key_hash(prefix, key_data)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with _LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            if not _init_vec(conn):
                return
            import sqlite_vec
            blob = sqlite_vec.serialize_float32(embedding)
            conn.execute(f"""
                INSERT OR REPLACE INTO {_VEC_TABLE} (key_hash, prefix, response, embedding, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (key_hash, prefix, response, blob, now))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()


def state_key_discovery(ddl_hash: str, use_db: bool = False, description_hash: str = "") -> str:
    """Ключ кэша состояния discovery: хеш DDL + хеш текстового описания (если «по описанию») + флаг БД.
    При изменении контекста запроса или описания кэш не переиспользуется."""
    return f"discovery:{ddl_hash}:desc={description_hash}:db={use_db}"


def state_key_analysis(ddl_hash: str, sizes_hash: str, params_hash: str) -> str:
    """Ключ кэша состояния анализа: ddl + размеры таблиц + параметры."""
    return f"analysis:{ddl_hash}:{sizes_hash}:{params_hash}"


def get_plan(query_hash: str, sizes_hash: str, ttl_days: Optional[int] = DEFAULT_TTL_DAYS) -> Optional[Dict[str, Any]]:
    """Получить кэшированный план EXPLAIN по хешу запроса и размеров (ускорение повторных расчётов)."""
    with _LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            row = conn.execute(
                "SELECT plan_json, created_at FROM plan_cache WHERE query_hash = ? AND sizes_hash = ?",
                (query_hash, sizes_hash),
            ).fetchone()
            if not row:
                return None
            plan_json, created_at = row[0], row[1]
            if ttl_days is not None and created_at:
                try:
                    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - created) > timedelta(days=ttl_days):
                        conn.execute(
                            "DELETE FROM plan_cache WHERE query_hash = ? AND sizes_hash = ?",
                            (query_hash, sizes_hash),
                        )
                        conn.commit()
                        return None
                except Exception:
                    pass
            try:
                return json.loads(plan_json)
            except Exception:
                return None
        finally:
            conn.close()


def set_plan(query_hash: str, sizes_hash: str, plan: Dict[str, Any]) -> None:
    """Сохранить план в кэш (EXPLAIN или синтез агента)."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with _LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            conn.execute(
                """INSERT OR REPLACE INTO plan_cache (query_hash, sizes_hash, plan_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (query_hash, sizes_hash, json.dumps(plan, ensure_ascii=False), now),
            )
            conn.commit()
        finally:
            conn.close()


def baseline_exists() -> bool:
    """Проверяет, есть ли сохранённый базовый снимок."""
    return _BASELINE_DB_PATH.exists()


def save_baseline() -> bool:
    """Сохраняет текущее состояние кэшей как базовое. При сбросе данные не будут удаляться ниже этого снимка.
    Включает: SQLite, JSON-кэш, agent_profiles.json, GIGACHAT_VERIFY_SSL_CERTS и др."""
    with _LOCK:
        try:
            if _DB_PATH.exists():
                import shutil
                shutil.copy2(str(_DB_PATH), str(_BASELINE_DB_PATH))
            _json_path = _CACHE_DIR / ".agent_cache.json"
            if _json_path.exists():
                import shutil
                shutil.copy2(str(_json_path), str(_BASELINE_JSON_PATH))
            else:
                _BASELINE_JSON_PATH.write_text("{}", encoding="utf-8")
            _save_baseline_config()
            return True
        except Exception:
            return False


def _save_baseline_config() -> None:
    """Сохраняет agent_profiles и конфиг в базовый снимок. Конфиг не опускается ниже _CORE_BASELINE."""
    try:
        profiles = list(_CORE_BASELINE["profiles"])
        if _AGENT_PROFILES_PATH.exists():
            with open(_AGENT_PROFILES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    profiles = data
        config = {**_CORE_BASELINE["config"]}
        config["GIGACHAT_VERIFY_SSL_CERTS"] = os.environ.get(
            "GIGACHAT_VERIFY_SSL_CERTS", _CORE_BASELINE["config"]["GIGACHAT_VERIFY_SSL_CERTS"]
        )
        _BASELINE_CONFIG_PATH.write_text(
            json.dumps({"profiles": profiles, "config": config}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _apply_baseline_config(profiles: list, cfg: dict) -> None:
    """Применяет профили и конфиг (запись в файл и os.environ)."""
    if isinstance(profiles, list):
        _AGENT_PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_AGENT_PROFILES_PATH, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
    for k, v in (cfg or {}).items():
        if v is not None:
            os.environ[k] = str(v)


def restore_baseline_config() -> bool:
    """Восстанавливает agent_profiles и конфиг. Если есть снимок — из него; иначе — только конфиг из ядра (профили не трогаем)."""
    try:
        if _BASELINE_CONFIG_PATH.exists():
            data = json.loads(_BASELINE_CONFIG_PATH.read_text(encoding="utf-8"))
            profiles = data.get("profiles", _CORE_BASELINE["profiles"])
            cfg = {**_CORE_BASELINE["config"], **data.get("config", {})}
            _apply_baseline_config(profiles, cfg)
        else:
            for k, v in _CORE_BASELINE["config"].items():
                if v is not None and (k not in os.environ or not os.environ[k]):
                    os.environ[k] = str(v)
        return True
    except Exception:
        return False


def ensure_baseline_config_exists() -> bool:
    """Гарантирует базовый снимок. Если нет файла — создаёт из ядра (_CORE_BASELINE)."""
    if _BASELINE_CONFIG_PATH.exists():
        return True
    try:
        _BASELINE_CONFIG_PATH.write_text(
            json.dumps(_CORE_BASELINE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


def _restore_table_from_baseline(conn: sqlite3.Connection, table: str) -> int:
    """Восстанавливает таблицу из baseline. Возвращает число записей после восстановления."""
    if not _BASELINE_DB_PATH.exists():
        return 0
    baseline_abs = str(_BASELINE_DB_PATH.resolve())
    try:
        conn.execute("ATTACH DATABASE ? AS bl", (baseline_abs,))
        conn.execute(f"DELETE FROM main.{table}")
        try:
            conn.execute(f"INSERT INTO main.{table} SELECT * FROM bl.{table}")
        except sqlite3.OperationalError:
            pass
        conn.execute("DETACH DATABASE bl")
        conn.commit()
        cur = conn.execute(f"SELECT COUNT(*) FROM main.{table}")
        return (cur.fetchone() or (0,))[0]
    except Exception:
        try:
            conn.execute("DETACH DATABASE bl")
        except Exception:
            pass
        return 0


def reset_vector_cache(restore_from_baseline_if_exists: bool = True) -> int:
    """Сбросить векторную базу. Если есть baseline — восстанавливает из него, иначе очищает."""
    if not _vec_available():
        return 0
    with _LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            if not _init_vec(conn):
                return 0
            if restore_from_baseline_if_exists and baseline_exists():
                n = _restore_table_from_baseline(conn, _VEC_TABLE)
                return -n  # отрицательное = восстановлено
            cur = conn.execute(f"SELECT COUNT(*) FROM {_VEC_TABLE}")
            n = (cur.fetchone() or (0,))[0]
            conn.execute(f"DELETE FROM {_VEC_TABLE}")
            conn.commit()
            return n
        finally:
            conn.close()


def reset_agent_cache(restore_from_baseline_if_exists: bool = True) -> int:
    """Сбросить кэш ответов. Если есть baseline — восстанавливает из него, иначе очищает."""
    with _LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            if restore_from_baseline_if_exists and baseline_exists():
                n1 = _restore_table_from_baseline(conn, "agent_exact_cache")
                n2 = _restore_table_from_baseline(conn, "plan_cache")
                n = -(n1 + n2)
            else:
                cur = conn.execute("SELECT COUNT(*) FROM agent_exact_cache")
                n_exact = (cur.fetchone() or (0,))[0]
                cur = conn.execute("SELECT COUNT(*) FROM plan_cache")
                n_plan = (cur.fetchone() or (0,))[0]
                conn.execute("DELETE FROM agent_exact_cache")
                conn.execute("DELETE FROM plan_cache")
                conn.commit()
                n = n_exact + n_plan
        finally:
            conn.close()
    # JSON: восстановить из baseline или очистить
    try:
        _json_path = _CACHE_DIR / ".agent_cache.json"
        if restore_from_baseline_if_exists and _BASELINE_JSON_PATH.exists():
            import shutil
            shutil.copy2(str(_BASELINE_JSON_PATH), str(_json_path))
        elif _json_path.exists():
            _json_path.write_text("{}", encoding="utf-8")
    except Exception:
        pass
    return n


def reset_state_cache(restore_from_baseline_if_exists: bool = True) -> int:
    """Сбросить кэш состояний discovery. Если есть baseline — восстанавливает из него, иначе очищает."""
    with _LOCK:
        conn = _get_conn()
        try:
            _init_db(conn)
            if restore_from_baseline_if_exists and baseline_exists():
                n = _restore_table_from_baseline(conn, "agent_state_cache")
                return -n
            cur = conn.execute("SELECT COUNT(*) FROM agent_state_cache")
            n = (cur.fetchone() or (0,))[0]
            conn.execute("DELETE FROM agent_state_cache")
            conn.commit()
            return n
        finally:
            conn.close()
