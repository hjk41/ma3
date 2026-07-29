#!/usr/bin/env bash
# =============================================================================
# Continuous off-host probe for ma3 SaaS (Phase 0 observability).
#
# Run this on a machine that is NOT the ma3.io application host so a full host
# outage is still detected. Intended for systemd timer / cron every ~60s.
#
# Required:
#   MA3_BASE_URL              e.g. https://ma3.io
#   MA3_EXPECT_INSTANCE_ID    e.g. ma3-v1-hk
#
# Optional:
#   MA3_EXPECT_PUBLIC_BASE_URL   default = MA3_BASE_URL
#   MA3_PROBE_STATE_DIR          default = /var/tmp/ma3-probe
#   MA3_PROBE_FAIL_THRESHOLD     consecutive failures before notify (default 3)
#   MA3_PROBE_WEBHOOK_URL        POST JSON on threshold breach / recovery
#   MA3_PROBE_DOCTOR=1           also call authed ma3_doctor (needs MA3_API_KEY)
#   MA3_API_KEY                  ops key for doctor (optional)
#   MA3_PROBE_DRY_RUN=1          print webhook body instead of POSTing
#
# Exit: 0 = this tick ok; 1 = this tick failed.
# Notifications fire when crossing the consecutive-failure threshold or when
# recovering from a notified failure streak.
#
# Decision record: docs/09-engineering/design-archive/25-metrics-slo-decisions.md
# =============================================================================
set -euo pipefail

: "${MA3_BASE_URL:?set MA3_BASE_URL}"
: "${MA3_EXPECT_INSTANCE_ID:?set MA3_EXPECT_INSTANCE_ID}"

export MA3_BASE_URL="${MA3_BASE_URL%/}"
export MA3_EXPECT_INSTANCE_ID
export MA3_EXPECT_PUBLIC_BASE_URL="${MA3_EXPECT_PUBLIC_BASE_URL:-${MA3_BASE_URL}}"

STATE_DIR="${MA3_PROBE_STATE_DIR:-/var/tmp/ma3-probe}"
FAIL_THRESHOLD="${MA3_PROBE_FAIL_THRESHOLD:-3}"
WEBHOOK_URL="${MA3_PROBE_WEBHOOK_URL:-}"
DOCTOR="${MA3_PROBE_DOCTOR:-0}"
DRY_RUN="${MA3_PROBE_DRY_RUN:-0}"

mkdir -p "${STATE_DIR}"
FAIL_FILE="${STATE_DIR}/consecutive_fails"
NOTIFIED_FILE="${STATE_DIR}/notified"
LAST_ERR_FILE="${STATE_DIR}/last_error.txt"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy || true

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

read_fails() {
  if [[ -f "${FAIL_FILE}" ]]; then cat "${FAIL_FILE}"; else echo 0; fi
}

write_fails() { echo "$1" >"${FAIL_FILE}"; }

notify() {
  local event="$1"
  local detail="$2"
  local body
  body="$(
    EVENT="${event}" DETAIL="${detail}" PROBE_TS="$(ts)" python3 - <<'PY'
import json, os
print(json.dumps({
    "event": os.environ["EVENT"],
    "service": "ma3",
    "base_url": os.environ.get("MA3_BASE_URL", ""),
    "instance_id": os.environ.get("MA3_EXPECT_INSTANCE_ID", ""),
    "detail": os.environ.get("DETAIL", ""),
    "ts": os.environ["PROBE_TS"],
}, ensure_ascii=False))
PY
  )"

  echo "$(ts) notify event=${event} detail=${detail}"
  if [[ -z "${WEBHOOK_URL}" ]]; then
    echo "$(ts) WARN: MA3_PROBE_WEBHOOK_URL unset; notification skipped" >&2
    return 0
  fi
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "DRY_RUN webhook body: ${body}"
    return 0
  fi
  curl -sf -X POST "${WEBHOOK_URL}" \
    -H 'Content-Type: application/json' \
    -d "${body}" >/dev/null \
    || echo "$(ts) WARN: webhook POST failed" >&2
}

check_healthz() {
  local tmp
  tmp="$(mktemp)"
  if ! curl -sf --max-time 15 "${MA3_BASE_URL}/healthz" -o "${tmp}"; then
    echo "healthz unreachable"
    rm -f "${tmp}"
    return 1
  fi
  if ! python3 - "${tmp}" <<'PY'
import json, os, sys
h = json.load(open(sys.argv[1]))
errs = []
if h.get("status") != "ok":
    errs.append(f"status={h.get('status')}")
if h.get("instance_id") != os.environ["MA3_EXPECT_INSTANCE_ID"]:
    errs.append(f"instance_id={h.get('instance_id')}")
if h.get("public_base_url") != os.environ["MA3_EXPECT_PUBLIC_BASE_URL"]:
    errs.append(f"public_base_url={h.get('public_base_url')}")
if "dev_auth" in set(h.get("features") or []):
    errs.append("dev_auth present")
if errs:
    print("; ".join(errs))
    sys.exit(1)
PY
  then
    rm -f "${tmp}"
    return 1
  fi
  rm -f "${tmp}"
  return 0
}

check_whoami() {
  local tmp
  tmp="$(mktemp)"
  if ! curl -sf --max-time 20 -X POST "${MA3_BASE_URL}/mcp" \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ma3_whoami","arguments":{}}}' \
    -o "${tmp}"; then
    echo "mcp whoami unreachable"
    rm -f "${tmp}"
    return 1
  fi
  if ! python3 - "${tmp}" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
if d.get("error"):
    print(d["error"])
    sys.exit(1)
if "result" not in d:
    print("missing result")
    sys.exit(1)
PY
  then
    rm -f "${tmp}"
    return 1
  fi
  rm -f "${tmp}"
  return 0
}

check_doctor() {
  [[ "${DOCTOR}" == "1" ]] || return 0
  [[ -n "${MA3_API_KEY:-}" ]] || { echo "doctor requested but MA3_API_KEY unset"; return 1; }
  local tmp
  tmp="$(mktemp)"
  if ! curl -sf --max-time 30 -X POST "${MA3_BASE_URL}/mcp" \
    -H 'Content-Type: application/json' \
    -H "X-API-Key: ${MA3_API_KEY}" \
    -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"ma3_doctor","arguments":{}}}' \
    -o "${tmp}"; then
    echo "mcp doctor unreachable"
    rm -f "${tmp}"
    return 1
  fi
  if ! python3 - "${tmp}" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
if d.get("error"):
    print(d["error"])
    sys.exit(1)
sc = (d.get("result") or {}).get("structuredContent") or {}
if sc.get("ok") is False:
    print(sc)
    sys.exit(1)
checks = sc.get("checks") or sc.get("doctor") or {}
if isinstance(checks, dict):
    bad = []
    for k, v in checks.items():
        if isinstance(v, dict) and v.get("ok") is False:
            bad.append(k)
        elif v in ("fail", "error", False):
            bad.append(k)
    if bad:
        print("doctor checks failed: " + ",".join(bad))
        sys.exit(1)
PY
  then
    rm -f "${tmp}"
    return 1
  fi
  rm -f "${tmp}"
  return 0
}

err=""
if ! out="$(check_healthz 2>&1)"; then
  err="healthz: ${out}"
elif ! out="$(check_whoami 2>&1)"; then
  err="whoami: ${out}"
elif ! out="$(check_doctor 2>&1)"; then
  err="doctor: ${out}"
fi

if [[ -n "${err}" ]]; then
  echo "$(ts) FAIL ${err}" | tee "${LAST_ERR_FILE}" >&2
  fails="$(read_fails)"
  fails=$((fails + 1))
  write_fails "${fails}"
  if (( fails >= FAIL_THRESHOLD )) && [[ ! -f "${NOTIFIED_FILE}" ]]; then
    notify "ma3_probe_fail" "${err} (consecutive=${fails})"
    touch "${NOTIFIED_FILE}"
  fi
  exit 1
fi

suffix=""
[[ "${DOCTOR}" == "1" ]] && suffix=" +doctor"
echo "$(ts) OK healthz+whoami${suffix} instance=${MA3_EXPECT_INSTANCE_ID}"
prev="$(read_fails)"
write_fails 0
if [[ -f "${NOTIFIED_FILE}" ]]; then
  notify "ma3_probe_recover" "recovered after consecutive_fails=${prev}"
  rm -f "${NOTIFIED_FILE}"
fi
exit 0
