#!/usr/bin/env bash
# Validate unified Cursor rules/skills across all projects (source = gp_dq).
set -uo pipefail

SOURCE="${RULES_VALIDATE_SOURCE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ROOT="${DCI_PROJECTS_ROOT:-$(cd "${SOURCE}/.." && pwd)}"
REG="${SOURCE}/.cursor/dci/projects.registry"
GLOBAL_ROUTER="${HOME}/.cursor/rules/team-command-router.mdc"

PASS=0
FAIL=0

pass() { echo "PASS  $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL  $1 — $2"; FAIL=$((FAIL + 1)); }

sha_file() {
  shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'
}

REQUIRED_RULES=(
  dialog-context-index.mdc
  tig-preflight-enforced.mdc
  tig-snapshot.mdc
)
REQUIRED_SKILLS=(
  dialog-context-index
  tig-snapshot
)
REQUIRED_SCRIPTS=(
  scripts/dci-vector.sh
  scripts/tig-context.sh
)

check_same_sha() {
  local id="$1" src="$2" dst="$3"
  if [[ ! -f "${dst}" ]]; then
    fail "${id}" "missing ${dst}"
    return
  fi
  local s1 s2
  s1="$(sha_file "${src}")"
  s2="$(sha_file "${dst}")"
  if [[ "${s1}" == "${s2}" ]]; then
    pass "${id}"
  else
    fail "${id}" "sha mismatch (run dci-propagate.sh)"
  fi
}

check_rule_contract() {
  local pid="$1" path="$2"
  local dci="${path}/.cursor/rules/dialog-context-index.mdc"
  if grep -q "Token read budget" "${dci}" && grep -q "TIG vs DCI" "${dci}"; then
    pass "${pid}-dci-token-contract"
  else
    fail "${pid}-dci-token-contract" "dialog-context-index missing Token read budget or TIG vs DCI"
  fi
  local skill="${path}/.cursor/skills/dialog-context-index/SKILL.md"
  if grep -q "## Token read budget" "${skill}" && grep -q "## Latency" "${skill}"; then
    pass "${pid}-dci-skill-contract"
  else
    fail "${pid}-dci-skill-contract" "DCI skill missing Token read budget or Latency"
  fi
}

check_router() {
  local pid="$1" path="$2"
  local local_router="${path}/.cursor/rules/team-command-router.mdc"
  local src_router="${SOURCE}/.cursor/rules/team-command-router.mdc"
  if [[ -f "${local_router}" ]] && grep -q "Team Router Inheritance" "${local_router}"; then
    if grep -q "TIG (project-local)" "${local_router}" && grep -q "DCI (project-local)" "${local_router}"; then
      pass "${pid}-router-inheritance-stub"
    else
      fail "${pid}-router-inheritance-stub" "stub missing DCI/TIG sections"
    fi
    check_same_sha "${pid}-router-global" "${src_router}" "${GLOBAL_ROUTER}"
  elif [[ -f "${local_router}" ]]; then
    check_same_sha "${pid}-router-full" "${src_router}" "${local_router}"
  else
    fail "${pid}-router" "team-command-router.mdc missing"
  fi
}

echo "=== Rules validate all projects $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "source: ${SOURCE}"

for rule in "${REQUIRED_RULES[@]}"; do
  [[ -f "${SOURCE}/.cursor/rules/${rule}" ]] || fail "source-${rule}" "missing in source"
done

while IFS= read -r line; do
  [[ "${line}" =~ ^# ]] && continue
  [[ -z "${line}" ]] && continue
  pid="${line%%|*}"
  path="${line#*|}"
  [[ -d "${path}/.cursor" ]] || continue

  echo "--- ${pid} ---"
  for rule in "${REQUIRED_RULES[@]}"; do
    check_same_sha "${pid}-${rule}" \
      "${SOURCE}/.cursor/rules/${rule}" \
      "${path}/.cursor/rules/${rule}"
  done
  for skill in "${REQUIRED_SKILLS[@]}"; do
    check_same_sha "${pid}-skill-${skill}" \
      "${SOURCE}/.cursor/skills/${skill}/SKILL.md" \
      "${path}/.cursor/skills/${skill}/SKILL.md"
  done
  for script in "${REQUIRED_SCRIPTS[@]}"; do
    check_same_sha "${pid}-${script//\//-}" \
      "${SOURCE}/${script}" \
      "${path}/${script}"
  done
  check_rule_contract "${pid}" "${path}"
  check_router "${pid}" "${path}"
done < "${REG}"

echo ""
echo "=== SUMMARY: PASS=${PASS} FAIL=${FAIL} ==="
[[ "${FAIL}" -eq 0 ]]
