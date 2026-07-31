#!/usr/bin/env bash
# Build a leak-free eval sandbox (no golden/, eval README, or ma3 hint files).
# Prints the absolute sandbox directory path on stdout.
set -euo pipefail

SCENARIO="${1:?scenario id, e.g. trigger-p2}"
RUN_TAG="${2:-sandbox}"

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SANDBOX_ROOT="${TRIGGER_SANDBOX_ROOT:-$EVAL_ROOT/results/trigger/sandboxes}"
SANDBOX_DIR="$SANDBOX_ROOT/${SCENARIO}-${RUN_TAG}"

wrap_dir_for() {
  local scenario="$1"
  case "$scenario" in
    trigger-p2) echo "$EVAL_ROOT/scenarios/compose-network-fix" ;;
    *)
      echo "unsupported sandbox scenario: $scenario" >&2
      return 1
      ;;
  esac
}

WRAP="$(wrap_dir_for "$SCENARIO")"
[[ -f "$WRAP/docker-compose.yml" ]] || { echo "missing compose in $WRAP" >&2; exit 1; }
[[ -f "$WRAP/broken/default.conf" ]] || { echo "missing broken config in $WRAP" >&2; exit 1; }

# Release :18081 from prior eval / sandbox stacks.
for dir in "$WRAP" "$SANDBOX_ROOT"/*; do
  [[ -f "${dir}/docker-compose.yml" ]] || continue
  (cd "$dir" && docker compose down -v --remove-orphans) >/dev/null 2>&1 || true
done

rm -rf "$SANDBOX_DIR"
mkdir -p "$SANDBOX_DIR/workspace"

cp "$WRAP/docker-compose.yml" "$SANDBOX_DIR/"
cp "$WRAP/broken/default.conf" "$SANDBOX_DIR/workspace/default.conf"
cp "$WRAP/verify.sh" "$SANDBOX_DIR/"
chmod +x "$SANDBOX_DIR/verify.sh"

# Neutral user prompt — no ma3 / golden / eval metadata.
cat >"$SANDBOX_DIR/prompt.txt" <<'EOF'
docker compose 起来的服务容器间互相 ping 不通，前端也访问不到后端，帮我修一下。
EOF

# Minimal in-sandbox context only (no solution steps).
cat >"$SANDBOX_DIR/NOTES.txt" <<'EOF'
Files in this directory:
- docker-compose.yml
- workspace/default.conf  (nginx config mounted into the frontend container)

The frontend is published on host port 18081.
EOF

(
  cd "$SANDBOX_DIR"
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  docker compose up -d --build
)
sleep 2

echo "sandbox ready: $SANDBOX_DIR" >&2
printf '%s\n' "$SANDBOX_DIR"
