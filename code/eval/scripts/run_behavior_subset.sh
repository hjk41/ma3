#!/usr/bin/env bash
# Weekly agent-behavior subset (claude × T2/T4/T5 by default).
# See docs/08-quality/testing/agent-eval-cadence.md
#
# Usage:
#   bash code/eval/scripts/run_behavior_subset.sh [--agent claude] [--tests T2,T4,T5] [--dry-run] [--out-dir DIR]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EVAL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

AGENT="claude"
TESTS_CSV="T2,T4,T5"
DRY_RUN=0
OUT_BASE="${EVAL_ROOT}/results/behavior"
MA3_BASE_URL="${MA3_BASE_URL:-http://127.0.0.1:8000}"

while [[ $# -gt 0 ]]; do
  case "$1" in
  --agent)
    AGENT="${2:?}"
    shift 2
    ;;
  --tests)
    TESTS_CSV="${2:?}"
    shift 2
    ;;
  --dry-run)
    DRY_RUN=1
    shift
    ;;
  --out-dir)
    OUT_BASE="${2:?}"
    shift 2
    ;;
  -h | --help)
    sed -n '2,8p' "$0"
    exit 0
    ;;
  *)
    echo "unknown arg: $1" >&2
    exit 2
    ;;
  esac
done

DATE_UTC="$(date -u +%Y-%m-%dT%H%M%SZ)"
RUN_ID="${DATE_UTC}-${AGENT}"
OUT_DIR="${OUT_BASE}/${DATE_UTC}-${AGENT}"
mkdir -p "${OUT_DIR}"

REPORT_JSON="${OUT_DIR}/report.json"
REPORT_MD="${OUT_DIR}/report.md"
HOST_NAME="$(hostname 2>/dev/null || echo unknown)"

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/load_secrets.sh" 2>/dev/null || true

declare -a TEST_IDS=()
IFS=',' read -r -a TEST_IDS <<<"${TESTS_CSV}"

results_tmp="$(mktemp)"
trap 'rm -f "${results_tmp}"' EXIT

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()[:-1] if False else sys.argv[1]))' "$1"
}

append_result() {
  local id="$1" status="$2" reason="$3" duration="$4" attempts="$5" evidence="$6"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "${id}" "${status}" "${reason}" "${duration}" "${attempts}" "${evidence}" >>"${results_tmp}"
}

preflight() {
  local id="$1"
  local reasons=()
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "dry-run"
    return 1
  fi
  if ! curl -sf "${MA3_BASE_URL}/healthz" >/dev/null 2>&1; then
    reasons+=("ma3_healthz_unreachable:${MA3_BASE_URL}")
  fi
  case "${id}" in
  T2 | T4)
    if ! command -v "${AGENT}" >/dev/null 2>&1 && [[ ! -x "${HOME}/.local/bin/${AGENT}" ]]; then
      reasons+=("agent_binary_missing:${AGENT}")
    fi
    if [[ "${id}" == "T2" ]] && ! command -v docker >/dev/null 2>&1; then
      reasons+=("docker_missing")
    fi
    if [[ ! -f "${EVAL_ROOT}/secrets/secrets.env" && ! -f "${HOME}/ma3/eval/secrets/secrets.env" ]]; then
      reasons+=("secrets_env_missing")
    fi
    ;;
  T5)
    if [[ -z "${MA3_KEY_CLAUDE_CODE:-${MA3_API_KEY:-}}" ]]; then
      reasons+=("api_key_env_missing")
    fi
    ;;
  esac
  if ((${#reasons[@]} > 0)); then
    local IFS=';'
    echo "${reasons[*]}"
    return 1
  fi
  echo "ok"
  return 0
}

run_t5() {
  local key="${MA3_KEY_CLAUDE_CODE:-${MA3_API_KEY:-}}"
  local body bad
  body="$(curl -sS -X POST "${MA3_BASE_URL}/mcp" \
    -H 'Content-Type: application/json' \
    -H "X-API-Key: ${key}" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ma3_whoami","arguments":{}}}' || true)"
  echo "${body}" | python3 -c 'import sys,json; d=json.load(sys.stdin); raise SystemExit(0 if "result" in d else 1)' || {
    echo "valid_key_no_result"
    return 1
  }
  bad="$(curl -sS -X POST "${MA3_BASE_URL}/mcp" \
    -H 'Content-Type: application/json' \
    -H 'X-API-Key: ma3k_invalid_key_for_t5' \
    -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"ma3_whoami","arguments":{}}}' || true)"
  echo "${bad}" | grep -q '"code":-32001' || {
    echo "bad_key_not_rejected"
    return 1
  }
  echo "whoami_ok_and_bad_key_rejected"
  return 0
}

run_t4() {
  # One agent invocation that should self-correct MCP validation errors.
  local prompt
  prompt="Call ma3 MCP tool ma3_report incorrectly nested under an 'arguments' envelope so you get -32602, then fix the payload using the error.message hint and succeed. Finally call ma3_whoami and print PASS."
  if [[ ! -x "${SCRIPT_DIR}/release_behavior_tests.sh" ]]; then
    echo "release_behavior_tests.sh missing"
    return 1
  fi
  bash "${SCRIPT_DIR}/release_behavior_tests.sh" "${AGENT}" run "${prompt}" >"${OUT_DIR}/t4-agent.log" 2>&1 || {
    echo "agent_run_failed; see t4-agent.log"
    return 1
  }
  if grep -qE 'PASS|whoami|principal_id' "${OUT_DIR}/t4-agent.log"; then
    echo "agent_log_ok"
    return 0
  fi
  echo "no_pass_marker; see t4-agent.log"
  return 1
}

run_t2() {
  local scenario="${EVAL_ROOT}/scenarios/mihomo-proxy"
  if [[ ! -d "${scenario}" ]]; then
    echo "scenario_missing:mihomo-proxy"
    return 1
  fi
  if [[ ! -x "${SCRIPT_DIR}/release_behavior_tests.sh" ]]; then
    echo "release_behavior_tests.sh missing"
    return 1
  fi
  (
    cd "${scenario}"
    bash setup.sh >/dev/null 2>&1 || true
  )
  local prompt
  prompt="Use ma3_context to find knowledge for this infra problem, apply the fix, verify, then upvote the useful record with ma3_feedback (do not create a duplicate ma3_report). Print PASS when done."
  bash "${SCRIPT_DIR}/release_behavior_tests.sh" "${AGENT}" run "${prompt}" >"${OUT_DIR}/t2-agent.log" 2>&1 || {
    echo "agent_run_failed; see t2-agent.log"
    return 1
  }
  if [[ -x "${scenario}/verify.sh" ]]; then
    (cd "${scenario}" && bash verify.sh >"${OUT_DIR}/t2-verify.log" 2>&1) || {
      echo "verify.sh_failed; see t2-verify.log"
      return 1
    }
  fi
  echo "scenario_verify_ok"
  return 0
}

run_one() {
  local id="$1"
  local t0 t1 dur attempts=1 status reason evidence
  t0="$(date +%s)"
  if ! reason="$(preflight "${id}")"; then
    t1="$(date +%s)"
    append_result "${id}" "SKIPPED" "${reason}" "$((t1 - t0))" "0" ""
    return 0
  fi
  evidence=""
  case "${id}" in
  T5)
    if evidence="$(run_t5)"; then status="PASS"; reason=""; else status="FAIL"; reason="${evidence}"; fi
    ;;
  T4)
    if evidence="$(run_t4)"; then
      status="PASS"
      reason=""
    else
      # one flake retry
      attempts=2
      if evidence="$(run_t4)"; then status="FLAKY"; reason="passed_on_retry"; else status="FAIL"; reason="${evidence}"; fi
    fi
    ;;
  T2)
    if evidence="$(run_t2)"; then
      status="PASS"
      reason=""
    else
      attempts=2
      if evidence="$(run_t2)"; then status="FLAKY"; reason="passed_on_retry"; else status="FAIL"; reason="${evidence}"; fi
    fi
    ;;
  *)
    status="SKIPPED"
    reason="unknown_test:${id}"
    evidence=""
    ;;
  esac
  t1="$(date +%s)"
  dur="$((t1 - t0))"
  append_result "${id}" "${status}" "${reason}" "${dur}" "${attempts}" "${evidence}"
}

for tid in "${TEST_IDS[@]}"; do
  tid="$(echo "${tid}" | tr -d '[:space:]')"
  [[ -n "${tid}" ]] || continue
  echo "==> ${tid}"
  run_one "${tid}"
done

REPORT_JSON="${REPORT_JSON}" REPORT_MD="${REPORT_MD}" RESULTS_TMP="${results_tmp}" \
  RUN_ID="${RUN_ID}" DATE_UTC="${DATE_UTC}" HOST_NAME="${HOST_NAME}" AGENT="${AGENT}" \
  MA3_BASE_URL="${MA3_BASE_URL}" DRY_RUN="${DRY_RUN}" \
  python3 - <<'PY'
import json, os, pathlib
rows = pathlib.Path(os.environ["RESULTS_TMP"]).read_text().splitlines()
tests = []
for line in rows:
    if not line.strip():
        continue
    tid, status, reason, dur, attempts, evidence = line.split("\t", 5)
    tests.append({
        "id": tid,
        "status": status,
        "reason": reason,
        "evidence": evidence,
        "duration_s": int(dur),
        "attempts": int(attempts),
    })
summary = {
    "pass": sum(1 for t in tests if t["status"] == "PASS"),
    "fail": sum(1 for t in tests if t["status"] == "FAIL"),
    "flaky": sum(1 for t in tests if t["status"] == "FLAKY"),
    "skipped": sum(1 for t in tests if t["status"] == "SKIPPED"),
}
doc = {
    "run_id": os.environ["RUN_ID"],
    "date": os.environ["DATE_UTC"],
    "host": os.environ["HOST_NAME"],
    "agent": os.environ["AGENT"],
    "ma3_base_url": os.environ["MA3_BASE_URL"],
    "dry_run": os.environ.get("DRY_RUN") == "1",
    "tests": tests,
    "summary": summary,
}
path = pathlib.Path(os.environ["REPORT_JSON"])
path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
md = [
    "# Behavior subset report",
    "",
    f"- run_id: `{doc['run_id']}`",
    f"- agent: `{doc['agent']}`",
    f"- dry_run: {doc['dry_run']}",
    "",
    "| Test | Status | Reason | Duration | Attempts |",
    "|---|---|---|---:|---:|",
]
for t in tests:
    md.append(
        f"| {t['id']} | {t['status']} | {t['reason'] or '—'} | {t['duration_s']} | {t['attempts']} |"
    )
md.append("")
md.append(f"Summary: {summary}")
pathlib.Path(os.environ["REPORT_MD"]).write_text("\n".join(md) + "\n", encoding="utf-8")
print(path)
print(os.environ["REPORT_MD"])
raise SystemExit(1 if summary["fail"] else 0)
PY
