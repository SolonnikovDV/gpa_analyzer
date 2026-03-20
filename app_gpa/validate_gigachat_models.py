#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка чат- и embedding-моделей из CHAT_MODEL_PRIORITY / EMBEDDING_MODEL_PRIORITY:
простой chat и один вызов embeddings на каждую модель.

Запуск (из корня репозитория):
  python app_gpa/validate_gigachat_models.py
или из app_gpa:
  python validate_gigachat_models.py

Креды: как у check_gigachat_connection.py (.key, .env, --token, client id/secret).
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_app_gpa = os.path.join(_script_dir, "app_gpa")
if os.path.isdir(_app_gpa):
    sys.path.insert(0, _app_gpa)
    _project_root = _script_dir
else:
    sys.path.insert(0, _script_dir)
    _project_root = os.path.dirname(_script_dir)

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
    if not os.path.isfile(key_path):
        return ""
    candidates = []
    with open(key_path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if len(s) >= 32 and re.match(r"^[A-Za-z0-9+/=]+$", s):
                return s
            candidates.append(s)
    return candidates[0] if candidates else ""


def _resolve_token(args: argparse.Namespace) -> tuple[str, str]:
    token = (args.token or "").strip()
    scope = (args.scope or "").strip() or os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS").strip() or "GIGACHAT_API_PERS"
    if not token and args.client_id and args.client_secret:
        raw = f"{args.client_id.strip()}:{args.client_secret.strip()}"
        token = base64.b64encode(raw.encode()).decode()
    if not token:
        token = _read_token_from_key(os.path.join(_project_root, ".key"))
    if not token:
        token = (os.environ.get("GIGACHAT_CREDENTIALS") or os.environ.get("GIGACHAT_TOKEN") or "").strip()
    if not token and os.environ.get("GIGACHAT_CLIENT_ID") and os.environ.get("GIGACHAT_CLIENT_SECRET"):
        raw = f"{os.environ['GIGACHAT_CLIENT_ID']}:{os.environ['GIGACHAT_CLIENT_SECRET']}"
        token = base64.b64encode(raw.encode()).decode()
    return token, scope


def _validate_chat(credentials: str, scope: str, model: str) -> tuple[bool, str]:
    from agent.gigachat_agent import _gigachat_client_kwargs
    from gigachat import GigaChat

    kw = _gigachat_client_kwargs(
        credentials_override=credentials,
        scope_override=scope,
        model_override=model,
    )
    if not kw:
        return False, "no credentials"
    prompt = 'Ответь одним словом на русском: результат 2+2 (только цифра).'
    try:
        with GigaChat(**kw) as giga:
            resp = giga.chat(prompt)
        text = ""
        if resp.choices:
            text = (resp.choices[0].message.content or "").strip()
        if not text:
            return False, "empty content"
        if not any(c.isdigit() for c in text):
            return False, f"unexpected: {text[:80]!r}"
        return True, text[:200]
    except Exception as e:
        return False, str(e).strip()[:500]


def _validate_embedding(credentials: str, scope: str, model: str) -> tuple[bool, str]:
    from agent.gigachat_agent import _gigachat_client_kwargs
    from gigachat import GigaChat

    kw = _gigachat_client_kwargs(
        credentials_override=credentials,
        scope_override=scope,
        model_override=model,
    )
    if not kw:
        return False, "no credentials"
    try:
        with GigaChat(**kw) as giga:
            r = giga.embeddings(["тест"])
        data = getattr(r, "data", None) or []
        if not data:
            return False, "empty data"
        emb = getattr(data[0], "embedding", None) or []
        dim = len(emb)
        if dim < 8:
            return False, f"vector dim too small: {dim}"
        return True, f"dim={dim}"
    except Exception as e:
        return False, str(e).strip()[:500]


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка моделей GigaChat из списков UI")
    parser.add_argument("--token", "-t", default="")
    parser.add_argument("--client-id", default="")
    parser.add_argument("--client-secret", default="")
    parser.add_argument("--scope", "-s", default="")
    parser.add_argument("--no-ssl-verify", action="store_true")
    args = parser.parse_args()

    if args.no_ssl_verify:
        os.environ["GIGACHAT_VERIFY_SSL_CERTS"] = "false"

    token, scope = _resolve_token(args)
    if not token:
        print("Нет ключа: .key, GIGACHAT_CREDENTIALS или --token / --client-id+--client-secret", file=sys.stderr)
        return 2

    from agent.gigachat_agent import CHAT_MODEL_PRIORITY, EMBEDDING_MODEL_PRIORITY

    print(f"Scope: {scope}")
    print("--- Чат (простая генерация) ---")
    chat_ok = 0
    for m in CHAT_MODEL_PRIORITY:
        ok, info = _validate_chat(token, scope, m)
        status = "OK " if ok else "FAIL"
        print(f"  [{status}] {m}: {info}")
        if ok:
            chat_ok += 1

    print("--- Эмбеддинги ---")
    emb_ok = 0
    for m in EMBEDDING_MODEL_PRIORITY:
        ok, info = _validate_embedding(token, scope, m)
        status = "OK " if ok else "FAIL"
        print(f"  [{status}] {m}: {info}")
        if ok:
            emb_ok += 1

    total = len(CHAT_MODEL_PRIORITY) + len(EMBEDDING_MODEL_PRIORITY)
    passed = chat_ok + emb_ok
    print(f"--- Итого: {passed}/{total} ---")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
