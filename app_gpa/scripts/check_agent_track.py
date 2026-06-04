#!/usr/bin/env python3
"""Smoke-check GPA agent track: governance, providers, optional API validate."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.compat import install_compat_imports

install_compat_imports()

import argparse
import json
import sys

from modules.agents.credentials import credentials_configured, resolve_credentials
from modules.agents.governance.job_context import governance_job_context
from modules.agents.governance.loader import load_manifest
from modules.agents.governance.registry import roles_for_step
from modules.agents.orchestrator import AgentOrchestrator
from modules.agents.providers.registry import list_providers


def _check_governance() -> int:
    manifest = load_manifest()
    team_id = manifest.get("team_id") or manifest.get("id")
    if not team_id:
        print("governance: FAIL — manifest missing team_id", file=sys.stderr)
        return 1
    roles = roles_for_step("blocks_and_objects", "greenplum")
    if not roles:
        print("governance: FAIL — no roles for blocks_and_objects", file=sys.stderr)
        return 1
    ctx = governance_job_context()
    print(
        "governance: OK — {team} v{ver} · steps={steps} · multi={ma}".format(
            team=ctx.get("governance_team_id"),
            ver=ctx.get("governance_version"),
            steps=len(manifest.get("steps") or {}),
            ma=ctx.get("multi_agent_enabled"),
        )
    )
    return 0


def _check_providers() -> int:
    providers = list_providers()
    if not providers:
        print("providers: FAIL — empty registry", file=sys.stderr)
        return 1
    configured = [p.id for p in providers if credentials_configured(p.id)]
    print(
        "providers: OK — "
        + ", ".join(f"{p.id}{'*' if credentials_configured(p.id) else ''}" for p in providers)
    )
    if not configured:
        print("providers: WARN — no credentials configured", file=sys.stderr)
    return 0


def _validate_provider(provider: str) -> int:
    creds = resolve_credentials(provider)
    if not creds:
        print(f"{provider}: SKIP — credentials not found", file=sys.stderr)
        return 3
    orch = AgentOrchestrator(provider=provider, credentials_override=creds)
    try:
        orch.validate()
        print(f"{provider}: OK")
        return 0
    except Exception as e:
        print(f"{provider}: FAIL — {e}", file=sys.stderr)
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(description="GPA agent track smoke check")
    parser.add_argument(
        "--validate",
        choices=("gigachat", "deepseek", "all"),
        help="optional live API validate",
    )
    parser.add_argument("--json", action="store_true", help="JSON summary on stdout")
    args = parser.parse_args()

    rc_gov = _check_governance()
    rc_prov = _check_providers()
    rc_val = 0
    if args.validate:
        targets = ["gigachat", "deepseek"] if args.validate == "all" else [args.validate]
        codes = [_validate_provider(t) for t in targets]
        rc_val = max(codes) if codes else 0

    rc = max(rc_gov, rc_prov, rc_val if args.validate else 0)
    if args.json:
        print(
            json.dumps(
                {
                    "governance_ok": rc_gov == 0,
                    "providers_ok": rc_prov == 0,
                    "validate_rc": rc_val if args.validate else None,
                    "exit_code": rc,
                },
                ensure_ascii=False,
            )
        )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
