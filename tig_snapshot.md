---
{
  "tig_cli_version": "1.5",
  "generated_at": "2026-06-03T09:45:37Z",
  "target": "/Users/dmitrysolonnikov/PycharmProjects/overhead_analyzer",
  "mode": "compact",
  "fingerprint": "sha256:b971cad970c8ff8e",
  "git_head": "16402985ad317a2426bf0da01cf15b42ce27b342",
  "git_dirty": true,
  "base_ref": "HEAD~1",
  "base_ref_note": "fallback:HEAD~1 (preferred 'origin/main' missing)",
  "file_count": 233,
  "total_files": 233
}
---

# TIG Snapshot

**Project:** `overhead_analyzer`
**Mode:** `compact` | **Fingerprint:** `sha256:b971cad970c8ff8e`
**Base ref:** `HEAD~1` (fallback:HEAD~1 (preferred 'origin/main' missing))

## Module map

| Module | Files | Size |
|--------|------:|-----:|
| `.cursor` | 37 | 164241 bytes |
| `.DS_Store` | 1 | 6148 bytes |
| `.github` | 1 | 650 bytes |
| `.gitignore` | 1 | 1445 bytes |
| `.key` | 1 | 394 bytes |
| `.runtime_store` | 2 | 32768 bytes |
| `app_gpa` | 172 | 1334057 bytes |
| `gpa_project_struct.md` | 1 | 1121732 bytes |
| `LICENSE` | 1 | 1074 bytes |
| `README.md` | 1 | 46380 bytes |
| `README_CUSTOM_RULES.md` | 1 | 3514 bytes |
| `scripts` | 12 | 145828 bytes |
| `tig_app_ru.py` | 1 | 40718 bytes |
| `todo.md` | 1 | 7473 bytes |

**Total:** 233 files

## Directory tree

*depth ≤ 2*

```text
overhead_analyzer/
├── .cursor/
│   ├── context/
│   │   ├── dialogs/ …
│   ├── dci/
│   │   ├── init/ …
│   ├── rules/
│   ├── skills/
│   │   ├── b2c-team/ …
│   │   ├── de-matrix-team/ …
│   │   ├── dialog-context-index/ …
│   │   ├── gpa-agent-team/ …
│   │   ├── presentation-team/ …
│   │   ├── sql-team/ …
│   │   ├── web-app-team/ …
├── .github/
│   ├── workflows/
├── .runtime_store/
│   ├── jobs_state/
│   │   ├── jobs/ …
│   ├── presets/
│   ├── app_state.sqlite3-shm
│   ├── app_state.sqlite3-wal
├── app_gpa/
│   ├── agent/
│   ├── api/
│   │   ├── routers/ …
│   ├── config/
│   ├── core/
│   ├── detailed/
│   │   ├── lint/ …
│   ├── infrastructure/
│   ├── modules/
│   │   ├── agents/ …
│   │   ├── analysis/ …
│   ├── scripts/
│   ├── services/
│   │   ├── agents/ …
│   │   ├── cache/ …
│   │   ├── runtime/ …
│   │   ├── sql/ …
│   ├── var/
│   │   ├── agent_cache/ …
│   ├── web/
│   │   ├── routes/ …
│   │   ├── static/ …
│   │   ├── templates/ …
│   ├── app_settings.py
│   ├── conftest.py
│   ├── main.py
│   ├── pytest.ini
│   ├── requirements.txt
│   ├── webapp.py
│   ├── worker.py
├── scripts/
│   ├── dci-propagate.sh
│   ├── dci-setup-projects.sh
│   ├── dci-test.sh
│   ├── dci-validate-all-projects.sh
│   ├── dci-vector.sh
│   ├── dci_embed_server.py
│   ├── dci_vector_sync.py
│   ├── rules-validate-all-projects.sh
│   ├── run-app.sh
│   ├── sync-to-pycharm.sh
│   ├── tig-context.sh
│   ├── tig-test.sh
├── .DS_Store
├── .gitignore
├── .key
├── gpa_project_struct.md
├── LICENSE
├── README.md
├── README_CUSTOM_RULES.md
├── tig_app_ru.py
├── todo.md
```

## Git evolution (compact)

```text
Корень: /Users/dmitrysolonnikov/PycharmProjects/overhead_analyzer

=== STATUS ===
M app_gpa/api/routers/agent.py
 M tig_delta.md
 M tig_snapshot.md

=== LOG (12 oneline) ===
1640298 (HEAD -> add_ai_analize_opt) ui + docs: harmonize light/dark ux and editor readability
72668e9 repair ai section
ffddf3c fix rules
60dd8c5 (origin/add_ai_analize_opt) add rules
1d33aa2 fast api refactoring
5180baa fast api refactoring
a6329d8 rem md
5b0107b ui + linter
4eb5b5f add agent func
7b7fb56 (master) update gitignore
f995ed4 Merge branch 'update-ui' into master
5999fb2 (origin/update-ui, update-ui) update gitignore
```

## File index (compressed)

### Changed (vs base ref)
- `app_gpa/web/static/home.css` (6540 bytes)
- `app_gpa/web/static/detailed.css` (38669 bytes)
- `app_gpa/web/static/styles.css` (35044 bytes)
- `app_gpa/web/static/ux.css` (16785 bytes)
- `app_gpa/web/templates/analysis/detailed_result.html` (65566 bytes)

### Notable files (largest / capped index)
- `gpa_project_struct.md` (1121732 bytes)
- `app_gpa/web/templates/analysis/detailed_input.html` (195636 bytes)
- `app_gpa/modules/analysis/detailed_analyzer.py` (116452 bytes)
- `scripts/dci_vector_sync.py` (90640 bytes)
- `app_gpa/modules/agents/gigachat_agent.py` (90075 bytes)
- `app_gpa/web/routes/analysis.py` (58137 bytes)
- `README.md` (46380 bytes)
- `tig_app_ru.py` (40718 bytes)
- `.runtime_store/app_state.sqlite3-shm` (32768 bytes)
- `app_gpa/modules/analysis/sql_validator.py` (30870 bytes)
- `app_gpa/modules/analysis/runtime_analyzers.py` (29097 bytes)
- `app_gpa/modules/agents/agent_cache_db.py` (28118 bytes)
- `app_gpa/modules/agents/agent_prompts.py` (28118 bytes)
- `.cursor/context/vector_fallback.jsonl` (26799 bytes)
- `app_gpa/web/templates/analysis/table_sizes.html` (26352 bytes)
- `app_gpa/web/routes/agent.py` (24540 bytes)
- `.cursor/skills/presentation-team/SKILL.md` (24128 bytes)
- `app_gpa/api/routers/agent.py` (23988 bytes)
- `app_gpa/modules/analysis/antipattern_detector.py` (19465 bytes)
- `.cursor/context/dci_test_cases.md` (17574 bytes)
- `app_gpa/modules/analysis/execute_parser.py` (17429 bytes)
- `app_gpa/modules/analysis/plan_adjuster.py` (16746 bytes)
- `app_gpa/modules/analysis/nested_block_extractor.py` (16419 bytes)
- `app_gpa/modules/analysis/block_parser.py` (16035 bytes)
- `app_gpa/web/context.py` (15454 bytes)
- `app_gpa/modules/analysis/runtime_registry.py` (15412 bytes)
- `.cursor/rules/team-command-router.mdc` (13497 bytes)
- `app_gpa/web/static/gpa-agent-setup.js` (13343 bytes)
- `app_gpa/web/static/gpa-ui.js` (12772 bytes)
- `app_gpa/modules/analysis/sql_completion.py` (12415 bytes)
- `scripts/dci-propagate.sh` (11824 bytes)
- `app_gpa/modules/analysis/temp_table_tracker.py` (11717 bytes)
- `.cursor/rules/dialog-context-index.mdc` (11435 bytes)
- `app_gpa/web/templates/analysis/reset_cache_modal.html` (10919 bytes)
- `scripts/dci-test.sh` (10769 bytes)
- `app_gpa/modules/analysis/runtime_preset_store.py` (10749 bytes)
- `app_gpa/services/agents/api.py` (9693 bytes)
- `app_gpa/web/templates/app/agent_context_modal.html` (9656 bytes)
- `app_gpa/web/templates/app/home.html` (9642 bytes)
- `.cursor/skills/b2c-team/SKILL.md` (9082 bytes)
- `.cursor/skills/sql-team/SKILL.md` (8475 bytes)
- `app_gpa/modules/analysis/lint/spark_linter.py` (8345 bytes)
- `.cursor/skills/de-matrix-team/SKILL.md` (8322 bytes)
- `.cursor/skills/web-app-team/SKILL.md` (8287 bytes)
- `app_gpa/modules/agents/orchestrator.py` (8287 bytes)

*+183 more files — see `tig_delta.md` git diff*