#!/usr/bin/env bash
# Deploy ma3_v1 to 192.168.31.202: stop legacy :8000, migrate in-place, start v1.
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-192.168.31.202}"
REMOTE_USER="${REMOTE_USER:-hct}"
REMOTE_DIR="${REMOTE_DIR:-/home/hct/ma3_v1}"
LEGACY_DIR="${LEGACY_DIR:-/home/hct/ma3}"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${MA3_PORT:-8000}"
SSH="ssh -i ${HOME}/.ssh/id_rsa -o ConnectTimeout=15"
RSYNC_SSH="ssh -i ${HOME}/.ssh/id_rsa"

RSYNC_EXCLUDES=(
  --exclude '.git'
  --exclude '.venv'
  --exclude '__pycache__'
  --exclude '*.pyc'
  --exclude '.pytest_cache'
  --exclude 'server/data'
  --exclude 'server/.venv'
  --filter 'P ma3.env'
  --filter 'P ma3.pid'
  --filter 'P data/'
)

echo "==> Sync ma3_v1 -> ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}"
rsync -avz -e "$RSYNC_SSH" --delete "${RSYNC_EXCLUDES[@]}" \
  "${LOCAL_DIR}/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

echo "==> Remote: stop legacy, deploy v1, migrate in-place"
$SSH "${REMOTE_USER}@${REMOTE_HOST}" bash -s <<REMOTE
set -euo pipefail
LEGACY_DIR="${LEGACY_DIR}"
REMOTE_DIR="${REMOTE_DIR}"
PORT="${PORT}"

set -a
source "\${LEGACY_DIR}/ma3.env"
set +a

cd "\${REMOTE_DIR}/code/server"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "==> Pre-deploy DB inventory"
export MA3_DATABASE_URL="\${MA3_DATABASE_URL}"
.venv/bin/python scripts/db_inventory.py -o /tmp/ma3-deploy-pre.json
python3 -m json.tool /tmp/ma3-deploy-pre.json

echo "==> Stop legacy uvicorn on port \${PORT}"
pkill -f "uvicorn app.main:app.*--port \${PORT}" || true
sleep 2

mkdir -p "\${REMOTE_DIR}/data"
if [[ -d "\${LEGACY_DIR}/data/hf-cache" ]]; then
  ln -sfn "\${LEGACY_DIR}/data/hf-cache" "\${REMOTE_DIR}/data/hf-cache"
fi

cat > "\${REMOTE_DIR}/ma3.env" <<ENV
MA3_DEV_AUTH=1
MA3_DEV_API_KEY=ma3dev
MA3_PORT=\${PORT}
MA3_DATABASE_URL=\${MA3_DATABASE_URL}
MA3_INSTANCE_ID=ma3-v1-202
MA3_HF_HOME=\${LEGACY_DIR}/data/hf-cache
HF_HOME=\${LEGACY_DIR}/data/hf-cache
HF_HUB_OFFLINE=1
ENV

# Optional Authing (Observatory login) — set in \${LEGACY_DIR}/ma3.env or shell env before deploy
if [[ -n "\${MA3_AUTHING_APP_ID:-}" && -n "\${MA3_AUTHING_APP_SECRET:-}" ]]; then
  cat >> "\${REMOTE_DIR}/ma3.env" <<AUTHING
MA3_AUTHING_ENABLED=\${MA3_AUTHING_ENABLED:-1}
MA3_AUTHING_ISSUER=\${MA3_AUTHING_ISSUER}
MA3_AUTHING_APP_ID=\${MA3_AUTHING_APP_ID}
MA3_AUTHING_APP_SECRET=\${MA3_AUTHING_APP_SECRET}
MA3_PUBLIC_BASE_URL=\${MA3_PUBLIC_BASE_URL:-http://127.0.0.1:\${PORT}}
MA3_AUTHING_REDIRECT_URI=\${MA3_AUTHING_REDIRECT_URI:-\${MA3_PUBLIC_BASE_URL:-http://127.0.0.1:\${PORT}}/auth/callback}
MA3_AUTH_ADMIN_USERS=\${MA3_AUTH_ADMIN_USERS:?MA3_AUTH_ADMIN_USERS required when Authing is enabled}
AUTHING
fi

echo "==> Ensure pgvector extension (needs DB superuser; app role ma3user cannot CREATE EXTENSION)"
MA3_DBNAME="\${MA3_DATABASE_URL##*/}"
MA3_DBNAME="\${MA3_DBNAME%%\?*}"
if sudo -n -u postgres psql -d "\${MA3_DBNAME}" -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null 2>&1; then
  echo "   pgvector extension ensured on \${MA3_DBNAME}"
else
  echo "   WARN: could not ensure pgvector extension (need passwordless sudo to postgres superuser); vector ANN search will be disabled and search falls back to FTS"
fi

echo "==> Backfill legacy tables into v1 schema (same DB)"
export MA3_DATABASE_URL="\${MA3_DATABASE_URL}"
export MA3_MIGRATE_RENAME=0
export MA3_MIGRATE_BACKFILL=1
export MA3_DISABLE_EMBEDDINGS=1
.venv/bin/python scripts/migrate_legacy_pg.py | tee /tmp/ma3-backfill.json
python3 -m json.tool /tmp/ma3-backfill.json

echo "==> Post-backfill DB inventory check (before start)"
.venv/bin/python scripts/db_inventory.py --compare /tmp/ma3-deploy-pre.json --backfill /tmp/ma3-backfill.json \
  -o /tmp/ma3-deploy-post-backfill.json

echo "==> Start ma3_v1 uvicorn"
set -a
source "\${REMOTE_DIR}/ma3.env"
set +a
nohup .venv/bin/python -m uvicorn app.main:app \
  --host 0.0.0.0 --port "\${PORT}" --app-dir . \
  > /tmp/ma3-v1-uvicorn.log 2>&1 &
echo \$! > "\${REMOTE_DIR}/ma3.pid"

echo "==> healthz (wait up to 180s — embedding model loads before accepting traffic)"
ready=0
for _ in \$(seq 1 90); do
  if curl -sf "http://127.0.0.1:\${PORT}/healthz" >/tmp/ma3-healthz.json 2>/dev/null; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "\$ready" -ne 1 ]]; then
  echo "healthz not ready after 180s" >&2
  tail -40 /tmp/ma3-v1-uvicorn.log >&2 || true
  exit 1
fi
python3 -m json.tool /tmp/ma3-healthz.json

echo "==> Post-deploy DB inventory check (service up)"
.venv/bin/python scripts/db_inventory.py --compare /tmp/ma3-deploy-pre.json --backfill /tmp/ma3-backfill.json \
  -o /tmp/ma3-deploy-post.json

echo "==> Integration verification (deploy/README.md: must pass before reporting to user)"
export MA3_BASE_URL="http://127.0.0.1:\${PORT}"
export MA3_API_KEY=ma3dev
export MA3_EXPECT_INSTANCE_ID=ma3-v1-202
export MA3_READY_TIMEOUT=180
export MA3_EXPECT_MIN_RECORDS="\$(python3 -c "import json; inv=json.load(open('/tmp/ma3-deploy-post.json')); print(inv['v1_records'])")"
export MA3_EXPECT_MIN_CASES="\$(python3 -c "import json; pre=json.load(open('/tmp/ma3-deploy-pre.json')); post=json.load(open('/tmp/ma3-deploy-post.json')); print(max(pre.get('v1_cases',0), post.get('v1_cases',0), 20))")"
export MA3_EXPECT_MIN_MIHOMO_HITS=1
export MA3_EXPECT_MIN_LIBRARIES=2
if [[ -f /home/hct/ma3-eval/profiles/claude/.claude.json ]]; then
  export MA3_EVAL_CLAUDE_KEY="\$(python3 -c "import json; print(json.load(open('/home/hct/ma3-eval/profiles/claude/.claude.json'))['mcpServers']['ma3']['headers']['X-API-Key'])" 2>/dev/null || true)"
fi
if [[ -x "\${REMOTE_DIR}/code/eval/scripts/bootstrap_agent_client_sync.sh" ]]; then
  echo "==> Bootstrap eval claude client sync"
  bash "\${REMOTE_DIR}/code/eval/scripts/bootstrap_agent_client_sync.sh" claude || true
fi
bash "\${REMOTE_DIR}/deploy/verify_ma3_v1.sh"
REMOTE

echo "==> Done: http://${REMOTE_HOST}:${PORT}/healthz"
