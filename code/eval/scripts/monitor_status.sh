#!/usr/bin/env bash
# Print one-line eval + ma3 status for watchdog / operator reports.
set -euo pipefail
EVAL_ROOT="${EVAL_ROOT:-$HOME/ma3/eval}"
MA3_BASE="${MA3_BASE_URL:-http://127.0.0.1:8000}"

ma3_ok=no
if curl -sf -m 5 "${MA3_BASE}/healthz" >/dev/null 2>&1; then
  ma3_ok=yes
fi

eval_running=no
if pgrep -f "$EVAL_ROOT/orchestrator/run_all_eval" >/dev/null \
  || pgrep -f "$EVAL_ROOT/orchestrator/run_eval.sh --scenario" >/dev/null; then
  eval_running=yes
fi

stats=$(EVAL_ROOT="$EVAL_ROOT" python3 - <<'PY'
import glob, json, os
EVAL_ROOT = os.environ.get("EVAL_ROOT", os.path.expanduser("~/ma3/eval"))
cfg = json.load(open(f"{EVAL_ROOT}/orchestrator/scenarios.json"))
order = cfg["agent_order"]
all_runs = []
for item in cfg["rotation"]:
    sid = item["id"]
    idx = order.index(item["first"])
    seq = [order[(idx + i) % 3] for i in range(3)]
    for r, a in enumerate(seq, 1):
        all_runs.append(f"eval-{sid}-{a}-r{r}")
done = fail = pending = 0
current = ""
for rid in all_runs:
    p = f"{EVAL_ROOT}/results/{rid}.json"
    if not os.path.exists(p):
        pending += 1
        if not current:
            current = rid
        continue
    d = json.load(open(p))
    if d.get("verify_pass") and d.get("duration_s", 0) >= 10:
        done += 1
    else:
        fail += 1
        if not current:
            current = rid
# detect active run from log tail
import subprocess
try:
    tail = subprocess.check_output(["tail", "-3", "/tmp/ma3-eval-full.log"], text=True, stderr=subprocess.DEVNULL)
    for line in reversed(tail.splitlines()):
        if "==> [eval-" in line:
            current = line.split("[")[1].split("]")[0]
            break
        if "========" in line and "/" in line:
            current = line.strip()
            break
except Exception:
    pass
print(f"{done}|{fail}|{pending}|{len(all_runs)}|{current}")
PY
)

IFS='|' read -r done fail pending total current <<< "$stats"
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "[$ts] ma3=$ma3_ok eval_running=$eval_running progress=${done}/${total}_pass fail_or_retry=$fail pending=$pending current=${current:-none}"
