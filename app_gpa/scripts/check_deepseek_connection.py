#!/usr/bin/env python3
"""Консольный smoke-тест DeepSeek: доступ, chat completion, usage и баланс."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.compat import install_compat_imports

install_compat_imports()

import argparse
import json
import sys

from modules.agents.credentials import resolve_credentials
from modules.agents.orchestrator import AgentOrchestrator
from modules.agents.providers.base import ChatMessage
from modules.agents.providers.registry import get_provider
from modules.agents.token_usage import fetch_deepseek_balance, get_last_request_usage, get_provider_totals


def _print_usage(label: str, usage: dict | None) -> None:
    if not usage:
        print(f"{label}: —")
        return
    print(
        f"{label}: in={usage.get('prompt_tokens', 0)} "
        f"out={usage.get('completion_tokens', 0)} "
        f"total={usage.get('total_tokens', 0)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test DeepSeek API client")
    parser.add_argument(
        "--prompt",
        default="Ответь одним словом: ping",
        help="Текст тестового запроса",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Модель (по умолчанию из DEEPSEEK_MODEL или deepseek-chat)",
    )
    parser.add_argument(
        "--balance-only",
        action="store_true",
        help="Только GET /user/balance, без chat",
    )
    parser.add_argument("--json", action="store_true", help="Вывод результата в JSON")
    args = parser.parse_args()

    creds = resolve_credentials("deepseek")
    if not creds:
        print("DEEPSEEK_TOKEN / DEEPSEEK_API_KEY не найден в .key или env", file=sys.stderr)
        return 1

    provider = get_provider("deepseek")
    model = args.model or provider.info().default_chat_model

    balance = fetch_deepseek_balance(creds)
    chat_result = None
    validate_error = None

    if not args.balance_only:
        orch = AgentOrchestrator(provider="deepseek", credentials_override=creds, model_override=model)
        try:
            orch.validate()
        except Exception as e:
            validate_error = str(e).strip() or type(e).__name__

        try:
            chat_result = provider.chat(
                [ChatMessage(role="user", content=args.prompt)],
                credentials=creds,
                model=model,
                max_tokens=64,
            )
        except Exception as e:
            if args.json:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "stage": "chat",
                            "error": str(e),
                            "balance": balance,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(f"DeepSeek chat: FAIL — {e}", file=sys.stderr)
            return 2

    totals = get_provider_totals("deepseek")
    last = get_last_request_usage("deepseek")

    if args.json:
        payload = {
            "ok": chat_result is not None or args.balance_only,
            "model": model,
            "validate_error": validate_error,
            "balance": balance,
            "totals": totals,
            "last_request": last,
        }
        if chat_result:
            payload["reply"] = (chat_result.text or "").strip()
            payload["usage"] = chat_result.usage
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["ok"] else 2

    print("=== DeepSeek smoke ===")
    print(f"model: {model}")
    if validate_error:
        print(f"validate (ping): WARN — {validate_error}")
    else:
        print("validate (ping): OK")

    if balance.get("ok"):
        cur = balance.get("currency") or "USD"
        total = balance.get("total_balance") or "0"
        print(
            f"balance: {total} {cur} "
            f"(granted={balance.get('granted_balance')}, topped_up={balance.get('topped_up_balance')}) "
            f"available={balance.get('is_available')}"
        )
    else:
        print(f"balance: FAIL — {balance.get('balance_error')}", file=sys.stderr)

    if chat_result:
        reply = (chat_result.text or "").strip()
        print(f"reply: {reply[:200]}")
        _print_usage("last request", chat_result.usage)
    _print_usage("totals (deepseek)", totals)
    _print_usage("last tracked", last)

    if chat_result:
        print("DeepSeek: OK")
        return 0
    if args.balance_only and balance.get("ok"):
        print("DeepSeek balance: OK")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
