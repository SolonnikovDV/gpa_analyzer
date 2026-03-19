#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт проверки подключения к GigaChat API.
Запуск из корня проекта: python app_gpa/check_gigachat_connection.py
Или из app_gpa: python check_gigachat_connection.py

Источники кредов (по приоритету):
  1. Аргументы: --token TOKEN или --client-id ID --client-secret SECRET [--scope SCOPE]
  2. Файл .key в корне проекта (первая непустая строка, похожая на base64, или строка ≥32 символов)
  3. .env: GIGACHAT_CREDENTIALS или GIGACHAT_TOKEN; либо GIGACHAT_CLIENT_ID + GIGACHAT_CLIENT_SECRET

При 401 «credentials doesn't match db data»: ключ не совпадает с данными в ЛК.
  → В личном кабинете developers.sber.ru: Настройки API → сгенерировать новый ключ (показывается один раз).
  → Либо передать Client ID и Client Secret: --client-id ID --client-secret SECRET
"""
import argparse
import base64
import os
import re
import sys

# Пути: скрипт может быть в корне проекта или в app_gpa
_script_dir = os.path.dirname(os.path.abspath(__file__))
_app_gpa = os.path.join(_script_dir, "app_gpa")
if os.path.isdir(_app_gpa):
    sys.path.insert(0, _app_gpa)
    _project_root = _script_dir
else:
    sys.path.insert(0, _script_dir)
    _project_root = os.path.dirname(_script_dir)

# Загрузка .env (корень проекта и app_gpa)
for _d in (_project_root, _script_dir):
    _env_path = os.path.join(_d, ".env")
    if os.path.isfile(_env_path):
        try:
            from dotenv import load_dotenv
            load_dotenv(_env_path)
        except ImportError:
            pass
        break


def _read_token_from_key(key_path: str) -> str:
    """Читает токен из .key: приоритет — строка, похожая на base64 (≥32 символов); иначе первая непустая."""
    if not os.path.isfile(key_path):
        return ""
    candidates = []
    with open(key_path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if len(s) >= 32 and re.match(r"^[A-Za-z0-9+/=]+$", s):
                return s  # сразу подходящая строка
            candidates.append(s)
    return candidates[0] if candidates else ""


def main():
    parser = argparse.ArgumentParser(
        description="Проверка подключения к GigaChat API",
        epilog="При 401 проверьте ключ в ЛК developers.sber.ru или используйте --client-id и --client-secret.",
    )
    parser.add_argument("--token", "-t", help="Ключ авторизации: Base64(ClientID:ClientSecret)")
    parser.add_argument("--client-id", help="Client ID из личного кабинета (в паре с --client-secret)")
    parser.add_argument("--client-secret", help="Client Secret из личного кабинета (в паре с --client-id)")
    parser.add_argument("--scope", "-s", default="", help="Scope: GIGACHAT_API_PERS, GIGACHAT_API_B2B, GIGACHAT_API_CORP")
    parser.add_argument("--verbose", "-v", action="store_true", help="Показать параметры подключения (без секрета)")
    parser.add_argument("--no-ssl-verify", action="store_true", help="Отключить проверку SSL (self signed cert)")
    args = parser.parse_args()

    if args.no_ssl_verify:
        os.environ["GIGACHAT_VERIFY_SSL_CERTS"] = "false"

    token = (args.token or "").strip()
    scope = (args.scope or "").strip() or os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS").strip() or "GIGACHAT_API_PERS"

    if not token and args.client_id and args.client_secret:
        try:
            raw = f"{args.client_id.strip()}:{args.client_secret.strip()}"
            token = base64.b64encode(raw.encode()).decode()
        except Exception as e:
            print(f"Ошибка формирования ключа: {e}")
            sys.exit(1)

    if not token:
        token = _read_token_from_key(os.path.join(_project_root, ".key"))
    if not token:
        token = (os.environ.get("GIGACHAT_CREDENTIALS") or os.environ.get("GIGACHAT_TOKEN") or "").strip()
    if not token and os.environ.get("GIGACHAT_CLIENT_ID") and os.environ.get("GIGACHAT_CLIENT_SECRET"):
        try:
            raw = f"{os.environ['GIGACHAT_CLIENT_ID']}:{os.environ['GIGACHAT_CLIENT_SECRET']}"
            token = base64.b64encode(raw.encode()).decode()
        except Exception:
            pass

    if not token:
        print("Ошибка: Токен не задан.")
        print("Задайте: --token TOKEN, или --client-id ID --client-secret SECRET,")
        print("  или положите ключ в .key (одна строка Base64), или GIGACHAT_CREDENTIALS в .env")
        sys.exit(1)

    print("Проверка подключения к GigaChat API…")
    print(f"  Scope: {scope}")
    if args.verbose:
        print(f"  Token (первые 12 символов): {token[:12]}…" if len(token) > 12 else "  Token: ***")

    try:
        from agent.gigachat_agent import validate_credentials
        validate_credentials(credentials_override=token, scope_override=scope)
        print("\n✓ Подключение успешно. Креды валидны.")
        sys.exit(0)
    except Exception as e:
        err_text = str(e)
        print(f"\n✗ Проверка не пройдена: {e}")
        if "401" in err_text and ("credentials" in err_text.lower() or "match" in err_text.lower() or "db data" in err_text.lower()):
            print("\nПодсказка (401): ключ не совпадает с данными в личном кабинете GigaChat.")
            print("  • Зайдите в developers.sber.ru → ваш проект → Настройки API.")
            print("  • Нажмите «Получить ключ» / сгенерируйте новый ключ (он показывается один раз).")
            print("  • Либо скопируйте Client ID и Client Secret и запустите:")
            print("    python app_gpa/check_gigachat_connection.py --client-id ВАШ_ID --client-secret ВАШ_SECRET")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
