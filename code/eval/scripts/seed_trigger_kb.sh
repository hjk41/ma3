#!/usr/bin/env bash
# Seed eval KB records for a trigger-p* scenario from seed_kb.json.
# After ma3_report, each seed is ma3_publish_record'd to status=active so
# agents can retrieve it via search_records (buffered ILIKE is too strict).
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$EVAL_ROOT/scripts/load_secrets.sh"

SCENARIO="${1:?scenario id required, e.g. trigger-p1}"
SCENARIO_DIR="$EVAL_ROOT/scenarios/$SCENARIO"
SEED_FILE="$SCENARIO_DIR/seed_kb.json"

export MA3_API_KEY="${MA3_API_KEY:-${MA3_KEY_CURSOR_CLI:-}}"
[[ -f "$SEED_FILE" ]] || { echo "missing $SEED_FILE" >&2; exit 1; }
[[ -n "$MA3_API_KEY" ]] || { echo "MA3_API_KEY or MA3_KEY_CURSOR_CLI required" >&2; exit 1; }

mkdir -p "$SCENARIO_DIR/workspace"
OUT="$SCENARIO_DIR/workspace/seeded_record_ids.json"
MA3_MCP="${MA3_BASE_URL:-http://127.0.0.1:8000}/mcp"

python3 - "$SEED_FILE" "$OUT" "$MA3_MCP" <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

seed_path, out_path, mcp_url = sys.argv[1:4]
key = os.environ["MA3_API_KEY"]

with open(seed_path, encoding="utf-8") as f:
    seed = json.load(f)

records = seed.get("records") or []
if not records:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "target_product": seed.get("target_product"),
            "target_component": seed.get("target_component"),
            "records": [],
        }, f, indent=2)
    print(f"no records to seed for {seed_path}")
    raise SystemExit(0)


def mcp(tool, arguments):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    req = urllib.request.Request(
        mcp_url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": key},
        method="POST",
    )
    # Bypass proxy for localhost MCP (experiment arm B0).
    if "127.0.0.1" in mcp_url or "localhost" in mcp_url:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=120) as resp:
            return json.load(resp)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def extract_record_id(result):
    content = (result.get("result") or {}).get("content") or []
    text = content[0].get("text", "") if content else ""
    structured = (result.get("result") or {}).get("structuredContent") or {}
    if structured.get("record_id"):
        return structured["record_id"]
    for token in text.replace('"', " ").split():
        if token.startswith(("vk_", "rec_")):
            return token.strip(".,)")
    return None


written = []
for rec in records:
    body = {
        "problem": rec["problem"],
        "outcome": rec.get("outcome", "resolved"),
        "result_summary": rec["result_summary"],
        "target_product": seed.get("target_product", "ma3-eval"),
        "target_component": seed.get("target_component", ""),
        "actions": rec.get("actions", []),
        "tags": rec.get("tags", []),
        "redaction_mode": "auto",
    }
    body["client_version"] = os.environ.get("MA3_CLIENT_VERSION", "1.0.0")
    mcp("ma3_validate", {"tool_name": "ma3_report", "arguments": body})
    result = mcp("ma3_report", body)
    record_id = extract_record_id(result)
    if not record_id:
        raise RuntimeError(f"could not parse record_id from ma3_report response: {result}")
    # Eval seeds must be active so agents can retrieve them via search_records
    # (buffered author-only ILIKE is too strict for paraphrased queries).
    pub = mcp(
        "ma3_publish_record",
        {"record_id": record_id, "client_version": body["client_version"]},
    )
    pub_status = ((pub.get("result") or {}).get("structuredContent") or {}).get("status")
    entry = {
        "seed_key": rec.get("seed_key"),
        "record_id": record_id,
        "problem": rec["problem"][:120],
        "publish_status": pub_status or "unknown",
    }
    written.append(entry)
    print(f"seeded {rec.get('seed_key')}: {record_id} publish={entry['publish_status']}")

with open(out_path, "w", encoding="utf-8") as f:
    json.dump({
        "target_product": seed.get("target_product"),
        "target_component": seed.get("target_component"),
        "records": written,
    }, f, indent=2)
print(f"wrote {out_path}")
PY
