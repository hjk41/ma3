#!/usr/bin/env bash
# Run trigger mechanism experiment sessions (A0 baseline) and record results.
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$EVAL_ROOT/scripts/load_secrets.sh"

ARM="${TRIGGER_ARM:-A0-baseline}"
RUNTIME="${TRIGGER_RUNTIME:-cursor-agent}"
ROUNDS="${TRIGGER_ROUNDS:-3}"
TIMEOUT_SEC="${TRIGGER_TIMEOUT_SEC:-900}"
RESULT_DIR="$EVAL_ROOT/results/trigger/sessions"
CSV="${TRIGGER_CSV:-$EVAL_ROOT/results/trigger/runs.csv}"
MANIFEST="$EVAL_ROOT/scenarios/trigger/manifest.json"

chmod +x "$EVAL_ROOT/scripts/setup_trigger_arm.sh"
if [[ "${TRIGGER_WORKER_MODE:-0}" != "1" ]]; then
  bash "$EVAL_ROOT/scripts/setup_trigger_arm.sh" "$ARM"
fi
# setup runs in subshell — load exported arm env
# shellcheck disable=SC1091
[[ -f "${HOME}/.ma3/trigger-experiment-backup/current-arm.env" ]] && source "${HOME}/.ma3/trigger-experiment-backup/current-arm.env"
if [[ "${TRIGGER_SESSION_PREFIX:-no}" != "yes" && "${TRIGGER_ARM_APPLIED:-}" == "A6-session-prompt" ]]; then
  export TRIGGER_SESSION_PREFIX=yes
fi
if [[ "${TRIGGER_WORKER_MODE:-0}" != "1" ]]; then
  trap 'bash "$EVAL_ROOT/scripts/setup_trigger_arm.sh" restore 2>/dev/null || true' EXIT
fi

export MA3_BASE_URL="${MA3_BASE_URL:-https://ma3.io}"
export MA3_API_KEY="${MA3_API_KEY:-${MA3_KEY_CURSOR_CLI:-}}"
if [[ -z "${MA3_API_KEY}" ]]; then
  echo "MA3_API_KEY or MA3_KEY_CURSOR_CLI required (no hardcoded default)" >&2
  exit 1
fi
export PATH="${HOME}/.local/bin:${HOME}/.npm-global/bin:${PATH}"
export NO_PROXY="127.0.0.1,localhost,192.168.0.0/16,10.0.0.0/8,${NO_PROXY:-}"
export no_proxy="$NO_PROXY"

mkdir -p "$RESULT_DIR" "$(dirname "$CSV")"
# policy installed by setup_trigger_arm.sh from synced skill bundle

if [[ ! -f "$CSV" ]] || ! head -1 "$CSV" | grep -q run_id; then
  echo "run_id,arm,runtime,prompt_id,scenario_id,started_at,session_id,seeded_record_ids,read_before_mutation,read_quality,kb_used,write_occurred,write_correct,task_pass,false_read,hook_false_block,duration_s,notes" >"$CSV"
fi

pick_scenarios() {
  python3 - <<'PY'
import json, os
manifest = json.load(open(os.environ["MANIFEST"]))
# Week-1 priority first, then rest
order = ["P1","P2","P4","P5","P6","P3"]
by_pid = {s["prompt_id"]: s["id"] for s in manifest["scenarios"]}
for pid in order:
    if pid in by_pid:
        print(by_pid[pid])
PY
}

expects_read() {
  local scenario="$1"
  python3 - <<PY
import json
m = json.load(open("$MANIFEST"))
for s in m["scenarios"]:
    if s["id"] == "$scenario":
        print("yes" if s["expects_read"] else "no")
        break
PY
}

expects_write() {
  local scenario="$1"
  python3 - <<PY
import json
m = json.load(open("$MANIFEST"))
for s in m["scenarios"]:
    if s["id"] == "$scenario":
        print(s["expects_write"])
        break
PY
}

run_cursor() {
  local prompt="$1"
  local out="$2"
  timeout "$TIMEOUT_SEC" cursor-agent -p --force --output-format json "$prompt" >"$out" 2>"${out}.err" || true
}

run_droid() {
  local prompt="$1"
  local out="$2"
  if command -v droid >/dev/null 2>&1; then
    timeout "$TIMEOUT_SEC" droid exec --auto high --output-format json "$prompt" >"$out" 2>"${out}.err" || true
  else
    echo '{"error":"droid_missing"}' >"$out"
  fi
}

run_codex() {
  local prompt="$1" out="$2"
  mkdir -p "$(dirname "$out")"
  local codex_bin
  codex_bin="$(command -v codex 2>/dev/null || true)"
  if [[ -z "$codex_bin" ]]; then
    echo '{"error":"codex_missing"}' >"$out"
    echo "codex_missing" >"${out}.err"
    return 0
  fi
  # Ensure DuckCoding token is visible to provider env_key
  if [[ -z "${DUCKCODING_CODEX_TOKEN:-}" && -f "${HOME}/.bashrc" ]]; then
    eval "$(grep -E '^export DUCKCODING_CODEX_TOKEN=' "${HOME}/.bashrc" | head -1)" || true
  fi
  # DuckCoding is unreachable without LAN proxy on this host (direct = Service unavailable).
  # Keep proxy scoped to the codex subprocess so local MCP (:8010) is not forced through it.
  local proxy="${DUCKCODING_HTTPS_PROXY:-${HTTPS_PROXY:-http://192.168.31.200:1080}}"
  local cwd="${TRIGGER_AGENT_CWD:-.}"
  (
    export DUCKCODING_CODEX_TOKEN
    export http_proxy="$proxy" https_proxy="$proxy" HTTP_PROXY="$proxy" HTTPS_PROXY="$proxy" ALL_PROXY="$proxy"
    export NO_PROXY="127.0.0.1,localhost,::1,${NO_PROXY:-}"
    export no_proxy="$NO_PROXY"
    cd "$cwd"
    # Avoid stdin hang; force full access for eval sandboxes.
    timeout "$TIMEOUT_SEC" "$codex_bin" exec \
      --skip-git-repo-check \
      --dangerously-bypass-approvals-and-sandbox \
      --json \
      "$prompt" </dev/null >"$out" 2>"${out}.err"
  ) || true
}

run_claude() {
  local prompt="$1"
  local out="$2"
  local claude_bin
  claude_bin="$(command -v claude 2>/dev/null || echo "${HOME}/.npm-global/bin/claude")"
  if [[ -x "$claude_bin" ]]; then
    if [[ -n "${TRIGGER_AGENT_CWD:-}" ]]; then
      (cd "$TRIGGER_AGENT_CWD" && timeout "$TIMEOUT_SEC" "$claude_bin" -p --dangerously-skip-permissions "$prompt" >"$out" 2>"${out}.err") || true
    else
      timeout "$TIMEOUT_SEC" "$claude_bin" -p --dangerously-skip-permissions "$prompt" >"$out" 2>"${out}.err" || true
    fi
  else
    echo '{"error":"claude_missing"}' >"$out"
  fi
}

extract_session_id() {
  python3 - <<'PY' "$1"
import json, re, sys
raw = open(sys.argv[1], encoding="utf-8", errors="replace").read().strip()
if not raw:
    print("")
    raise SystemExit(0)
# Prefer primary UUID sessions over Claude subagent ids (agent-*).
# Collect in order of appearance; pick best, not merely the last JSON line.
uuid_re = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)
cands = []
for chunk in raw.splitlines():
    chunk = chunk.strip()
    if not chunk.startswith("{"):
        continue
    try:
        obj = json.loads(chunk)
    except json.JSONDecodeError:
        continue
    sid = obj.get("session_id") or obj.get("conversation_id") or obj.get("sessionId")
    if sid:
        cands.append(str(sid))
if not cands:
    print("")
    raise SystemExit(0)
primary = [s for s in cands if uuid_re.match(s) and not s.startswith("agent-")]
if primary:
    print(primary[0])
elif any(not s.startswith("agent-") for s in cands):
    print(next(s for s in cands if not s.startswith("agent-")))
else:
    print(cands[0])
PY
}

wait_transcript() {
  local sid="$1"
  local runtime="$2"
  local i hit
  for i in $(seq 1 30); do
    case "$runtime" in
      cursor-agent)
        hit=$(find "${HOME}/.cursor/projects" -path "*/agent-transcripts/${sid}/${sid}.jsonl" 2>/dev/null | head -1 || true)
        ;;
      droid)
        hit=$(find "${HOME}/.factory/sessions" -name "${sid}.jsonl" 2>/dev/null | head -1 || true)
        ;;
      claude)
        hit=$(find "${HOME}/.claude/projects" -name "${sid}.jsonl" 2>/dev/null | head -1 || true)
        ;;
      codex)
        # Codex sessions live under ~/.codex; best-effort newest jsonl
        hit=$(find "${HOME}/.codex" -name '*.jsonl' -mmin -60 2>/dev/null | sort | tail -1 || true)
        ;;
      *)
        hit=""
        ;;
    esac
    if [[ -n "$hit" && -s "$hit" ]]; then
      echo "$hit"
      return 0
    fi
    sleep 2
  done
  return 1
}

run_one() {
  local scenario="$1"
  local round="$2"
  local scenario_dir="$EVAL_ROOT/scenarios/$scenario"
  local prompt_id
  prompt_id=$(python3 - <<PY
import json
m=json.load(open("$MANIFEST"))
for s in m["scenarios"]:
    if s["id"]=="$scenario":
        print(s["prompt_id"]); break
PY
)
  local run_id="${ARM}-${RUNTIME}-${scenario}-r${round}"
  local started_at
  started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local t0
  t0=$(date +%s)

  echo ""
  echo "======== $run_id ========"

  rm -f "${HOME}/.ma3/session-state"/*.json 2>/dev/null || true

  local work_dir="$scenario_dir"
  unset TRIGGER_AGENT_CWD
  if [[ "${TRIGGER_USE_SANDBOX:-0}" == "1" ]]; then
    chmod +x "$EVAL_ROOT/scripts/setup_trigger_sandbox.sh"
    work_dir="$(bash "$EVAL_ROOT/scripts/setup_trigger_sandbox.sh" "$scenario" "$run_id")"
    TRIGGER_AGENT_CWD="$work_dir"
    export TRIGGER_AGENT_CWD
    echo "sandbox work_dir=$work_dir"
  elif [[ -x "$scenario_dir/setup.sh" ]]; then
    bash "$scenario_dir/setup.sh"
  fi

  # File-edit scenarios: run the agent with CWD = scenario dir so relative
  # paths like workspace/.npmrc resolve without relying on absolute 工作目录 alone.
  if [[ -z "${TRIGGER_AGENT_CWD:-}" ]]; then
    case "$scenario" in
      trigger-p1|trigger-p5|trigger-p6)
        TRIGGER_AGENT_CWD="$scenario_dir"
        export TRIGGER_AGENT_CWD
        ;;
    esac
  fi

  local seeded=""
  if [[ -f "$scenario_dir/seed_kb.json" ]] && python3 -c "import json; r=json.load(open('$scenario_dir/seed_kb.json')).get('records',[]); exit(0 if r else 1)"; then
    bash "$EVAL_ROOT/scripts/seed_trigger_kb.sh" "$scenario" || true
    seeded=$(python3 -c "import json; d=json.load(open('$scenario_dir/workspace/seeded_record_ids.json')); print(','.join(r.get('record_id','') for r in d.get('records',[])))" 2>/dev/null || true)
  fi

  local prompt
  if [[ -f "$work_dir/prompt.txt" ]]; then
    prompt=$(cat "$work_dir/prompt.txt")
  else
    prompt=$(cat "$scenario_dir/prompt.txt")
  fi
  if [[ "${TRIGGER_SESSION_PREFIX:-no}" == "yes" ]]; then
    prompt="[ma3-reminder] This environment has ma3 MCP. On non-trivial tasks, call ma3_context before web search, package installs, or config edits.

${prompt}"
  fi
  if [[ "${TRIGGER_USE_SANDBOX:-0}" == "1" ]]; then
    prompt="$prompt

工作目录: $work_dir
只能在此目录内查看和修改文件，不要访问该目录之外的路径。"
  else
    case "$scenario" in
      trigger-p2|trigger-p3|trigger-p5|trigger-p6)
        prompt="$prompt

工作目录: $scenario_dir"
        ;;
    esac
  fi

  local agent_out="$RESULT_DIR/${run_id}.json"
  case "$RUNTIME" in
    cursor-agent) run_cursor "$prompt" "$agent_out" ;;
    droid) run_droid "$prompt" "$agent_out" ;;
    claude) run_claude "$prompt" "$agent_out" ;;
    codex) run_codex "$prompt" "$agent_out" ;;
    *) echo "unknown runtime: $RUNTIME" >&2; return 1 ;;
  esac

  local duration=$(( $(date +%s) - t0 ))
  local session_id
  session_id=$(extract_session_id "$agent_out")

  local task_pass=0
  if [[ -x "$work_dir/verify.sh" ]]; then
    if bash "$work_dir/verify.sh"; then task_pass=1; fi
  elif [[ -x "$scenario_dir/verify.sh" ]]; then
    if bash "$scenario_dir/verify.sh"; then task_pass=1; fi
  else
    task_pass=1
  fi

  local metrics_json=""
  local transcript=""
  if [[ -n "$session_id" ]]; then
    transcript=$(wait_transcript "$session_id" "$RUNTIME" || true)
  fi
  if [[ -z "$transcript" && "$RUNTIME" == "claude" ]]; then
    transcript=$(find "${HOME}/.claude/projects" -name '*.jsonl' -mmin -30 2>/dev/null | sort | tail -1 || true)
  fi
  if [[ -n "$transcript" ]]; then
    metrics_json=$(python3 "$EVAL_ROOT/scripts/analyze_trigger_run.py" \
      --transcript "$transcript" --scenario "$scenario" \
      --expects-read "$(expects_read "$scenario")" 2>/dev/null || true)
    if [[ -z "$session_id" && -n "$transcript" ]]; then
      session_id=$(basename "$transcript" .jsonl)
    fi
  fi

  local read_before="" read_quality="" write_occ="" false_read="" notes=""
  if [[ -n "$metrics_json" ]]; then
    read_before=$(echo "$metrics_json" | python3 -c "import sys,json; d=json.load(sys.stdin); v=d.get('read_before_mutation'); print('1' if v else '0' if v is not None else '')")
    read_quality=$(echo "$metrics_json" | python3 -c "import sys,json; d=json.load(sys.stdin); v=d.get('read_quality_ok'); print('1' if v else '0' if v is not None else '')")
    write_occ=$(echo "$metrics_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print('1' if d.get('ma3_write_calls',0)>0 else '0')")
    false_read=$(echo "$metrics_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print('1' if d.get('false_read') else '0')")
    notes=$(echo "$metrics_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"ctx={d.get('ma3_context_calls')} write={d.get('ma3_write_calls')} mut_idx={d.get('first_mutating_idx')}\")")
  else
    notes="no_transcript_metrics runtime=$RUNTIME"
  fi

  local write_correct=""
  local expect_w
  expect_w=$(expects_write "$scenario")
  if [[ "$write_occ" == "1" ]]; then
    case "$expect_w" in
      none) write_correct=0 ;;
      feedback_upvote|feedback_upvote_or_new|report_new) write_correct=1 ;;
      *) write_correct="" ;;
    esac
  elif [[ "$expect_w" == "none" ]]; then
    write_correct=1
  else
    write_correct=0
  fi

  echo "$run_id,$ARM,$RUNTIME,$prompt_id,$scenario,$started_at,$session_id,$seeded,$read_before,$read_quality,,$write_occ,$write_correct,$task_pass,$false_read,,$duration,$notes" >>"$CSV"
  echo "done $run_id task_pass=$task_pass duration=${duration}s session=$session_id"
}

export MANIFEST
SCENARIOS="${TRIGGER_SCENARIOS:-$(pick_scenarios)}"
echo "======== trigger arm: $ARM runtime=$RUNTIME base=$MA3_BASE_URL scenarios=$SCENARIOS session_prefix=${TRIGGER_SESSION_PREFIX:-no} sandbox=${TRIGGER_USE_SANDBOX:-0} ========"

round_list() {
  if [[ -n "${TRIGGER_ROUND:-}" ]]; then
    echo "$TRIGGER_ROUND"
  else
    seq 1 "$ROUNDS"
  fi
}

for scenario in $SCENARIOS; do
  for round in $(round_list); do
    run_one "$scenario" "$round"
  done
done

python3 "$EVAL_ROOT/scripts/aggregate_trigger_results.py" --runs "$CSV" --out "$EVAL_ROOT/results/trigger/summary.md" \
  || echo "warn: aggregate_trigger_results.py failed (non-fatal)" >&2
echo "Wrote $CSV and summary.md"
