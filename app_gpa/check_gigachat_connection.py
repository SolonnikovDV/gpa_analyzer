#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт проверки подключения к GigaChat API.
Запуск из корня проекта: python app_gpa/check_gigachat_connection.py
Или из app_gpa: python check_gigachat_connection.py

Источники кредов (по приоритету):
  1. Аргументы: --token TOKEN [--scope SCOPE]
  2. Файл .key в корне проекта (первая строка = token)
  3. .env: GIGACHAT_CREDENTIALS или GIGACHAT_TOKEN, GIGACHAT_SCOPE
"""
import argparse
import os
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


def main():
    parser = argparse.ArgumentParser(description="Проверка подключения к GigaChat API")
    parser.add_argument("--token", "-t", help="Token (Base64(ClientID:ClientSecret))")
    parser.add_argument("--scope", "-s", default="", help="Scope: GIGACHAT_API_PERS, GIGACHAT_API_B2B, GIGACHAT_API_CORP")
    parser.add_argument("--verbose", "-v", action="store_true", help="Показать параметры подключения (без токена)")
    parser.add_argument("--no-ssl-verify", action="store_true", help="Отключить проверку SSL (self signed cert)")
    args = parser.parse_args()

    if args.no_ssl_verify:
        os.environ["GIGACHAT_VERIFY_SSL_CERTS"] = "false"

    token = (args.token or "").strip()
    scope = (args.scope or "").strip() or os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS").strip() or "GIGACHAT_API_PERS"

    if not token:
        key_path = os.path.join(_project_root, ".key")
        if os.path.isfile(key_path):
            with open(key_path, "r", encoding="utf-8") as f:
                token = (f.read().split("\n")[0] or "").strip()
        if not token:
            token = (os.environ.get("GIGACHAT_CREDENTIALS") or os.environ.get("GIGACHAT_TOKEN") or "").strip()

    if not token:
        print("Ошибка: Token не задан.")
        print("Задайте через: --token TOKEN, файл .key (первая строка) или GIGACHAT_CREDENTIALS в .env")
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
        print(f"\n✗ Проверка не пройдена: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
