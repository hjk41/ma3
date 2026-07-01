#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCENARIO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROFILES=(cursor codex claude droid)
PHASE="${VERIFY_PHASE:-all}"
EXPECT="${MA3_EXPECT_SKILL_VERSION:?MA3_EXPECT_SKILL_VERSION required}"

echo "==> agent-client-sync verify phase=${PHASE} expect_skill=${EXPECT}"

for _ in $(seq 1 60); do
  if curl -sf "${MA3_BASE_URL}/healthz" >/dev/null; then
    break
  fi
  sleep 1
done
curl -sf "${MA3_BASE_URL}/healthz" >/dev/null

MANIFEST_SKILL="$(curl -sf "${MA3_BASE_URL}/client/manifest.json" | jq -r .skill_bundle_version)"
if [[ "${MANIFEST_SKILL}" != "${EXPECT}" ]]; then
  echo "FAIL server manifest skill_bundle_version=${MANIFEST_SKILL} expected=${EXPECT}" >&2
  exit 1
fi

if [[ "${PHASE}" == "install" || "${PHASE}" == "all" ]]; then
  for agent in "${PROFILES[@]}"; do
    bash "${SCRIPT_DIR}/install_agent.sh" "${SCENARIO_DIR}/profiles/${agent}.profile"
    bash "${SCRIPT_DIR}/assert_agent.sh" "${SCENARIO_DIR}/profiles/${agent}.profile" "${EXPECT}"
  done
fi

if [[ "${PHASE}" == "upgrade" || "${PHASE}" == "all" ]]; then
  if [[ "${PHASE}" == "all" ]]; then
    echo "==> (all) upgrade phase uses same EXPECT; run host run.sh for version bump between phases"
  fi
  for agent in "${PROFILES[@]}"; do
    bash "${SCRIPT_DIR}/upgrade_agent.sh" "${SCENARIO_DIR}/profiles/${agent}.profile"
    bash "${SCRIPT_DIR}/assert_agent.sh" "${SCENARIO_DIR}/profiles/${agent}.profile" "${EXPECT}"
  done
fi

echo "==> all agent profiles passed (${#PROFILES[@]} agents, phase=${PHASE})"
