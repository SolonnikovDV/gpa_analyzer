---
name: gpa-agent-team
description: GPA runtime agent team — SQL, Greenplum/Spark/PySpark, DE, DBA, reviewer, critic, arbiter. Source of truth in app_gpa/agent/governance/. Used by Flask app and Cursor.
---

# GPA Agent Team (repository skill)

**Canonical path:** `app_gpa/agent/governance/`

Runtime приложение загружает этот skill через `agent.governance.loader.load_skill_markdown()`.

## Trigger

- Трек GPA: prepare → discovery → analysis с агентом
- Cursor: `команда: gpa-agent` / auto при работе над agent track

## Team (manifest.json)

Core: sql_developer, data_engineer, analytics_engineer, dba, reviewer, critic, arbiter, registry_steward.

Stack extras:
- greenplum → greenplum_developer
- spark → spark_engineer
- pyspark → pyspark_engineer

## Track steps → roles

See `manifest.json` → `track_steps`.

## Multi-agent

Policy in `manifest.json` → `multi_agent`. Runtime: `agent.governance.multi_agent_policy`.

## Do not duplicate

Edit roles in `governance/roles/*.md` and `manifest.json` only. Cursor copies in `.cursor/skills/` are pointers.
