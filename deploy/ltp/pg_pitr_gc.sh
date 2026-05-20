#!/usr/bin/env bash
# pg_pitr_gc.sh — Garbage-collect old basebackups + cross-instance WAL
# directories on CephFS. Idempotent and safe to run any time.
#
# Behavior:
#   - For the current instance: keep MA3_PG_BASEBACKUP_RETENTION newest
#     basebackups; remove older.
#   - Remove WAL segments in $MA3_PG_ARCHIVE_DIR older than the oldest
#     surviving basebackup of THIS instance.
#   - For other instances under $MA3_BACKUP_DIR/wal/: remove the whole
#     dir if its newest WAL segment is older than
#     MA3_PG_OLD_INSTANCE_RETENTION_DAYS, EXCEPT when the dir is the
#     basebackup_instance recorded in pitr_manifest.json (always kept).
#   - Update pitr_manifest.json's wal_dirs to drop pruned entries.
#
# Env consumed:
#   MA3_BACKUP_DIR
#   MA3_INSTANCE_ID
#   MA3_PG_ARCHIVE_DIR
#   MA3_PG_BASEBACKUP_RETENTION   (default 4)
#   MA3_PG_OLD_INSTANCE_RETENTION_DAYS  (default 7)

set -euo pipefail
IFS=$'\n\t'

log() { printf '[%s] pg_pitr_gc: %s\n' "$(date -u +%FT%TZ)" "$*" >&2; }

: "${MA3_BACKUP_DIR:?MA3_BACKUP_DIR required}"
: "${MA3_INSTANCE_ID:?MA3_INSTANCE_ID required}"
: "${MA3_PG_ARCHIVE_DIR:=$MA3_BACKUP_DIR/wal/$MA3_INSTANCE_ID}"
RETENTION="${MA3_PG_BASEBACKUP_RETENTION:-4}"
DAYS="${MA3_PG_OLD_INSTANCE_RETENTION_DAYS:-7}"

base_root="$MA3_BACKUP_DIR/basebackups/$MA3_INSTANCE_ID"
manifest="$MA3_BACKUP_DIR/pitr_manifest.json"

# 1) Retain N newest basebackups of THIS instance
if [[ -d "$base_root" ]]; then
  mapfile -t bbs < <(find "$base_root" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
    | sort -rn | awk '{print $2}')
  total=${#bbs[@]}
  if (( total > RETENTION )); then
    for ((i=RETENTION; i<total; i++)); do
      log "GC: removing old basebackup ${bbs[i]}"
      rm -rf -- "${bbs[i]}"
    done
  fi
fi

# 2) Determine oldest surviving basebackup time for this instance — used
#    as the WAL retention floor.
floor_epoch=0
if [[ -d "$base_root" ]]; then
  oldest=$(find "$base_root" -mindepth 1 -maxdepth 1 -type d -printf '%T@\n' \
    | sort -n | head -1 || true)
  if [[ -n "$oldest" ]]; then
    floor_epoch="${oldest%.*}"
  fi
fi

# 3) Prune old WAL segments under THIS instance's archive dir
if (( floor_epoch > 0 )) && [[ -d "$MA3_PG_ARCHIVE_DIR" ]]; then
  while IFS= read -r -d '' f; do
    log "GC: removing pre-floor WAL $f"
    rm -f -- "$f"
  done < <(find "$MA3_PG_ARCHIVE_DIR" -maxdepth 1 -type f \! -newermt "@$floor_epoch" -print0)
fi

# 4) Cross-instance WAL dir GC
keep_inst=""
if [[ -f "$manifest" ]]; then
  keep_inst=$(python3 -c "
import json,sys
try:
  d=json.load(open('$manifest'))
  print(d.get('basebackup_instance_id') or '')
except Exception:
  print('')
" 2>/dev/null || true)
fi
cutoff_epoch=$(( $(date -u +%s) - DAYS*86400 ))

if [[ -d "$MA3_BACKUP_DIR/wal" ]]; then
  while IFS= read -r d; do
    inst=$(basename "$d")
    [[ "$inst" == "$MA3_INSTANCE_ID" ]] && continue
    [[ -n "$keep_inst" && "$inst" == "$keep_inst" ]] && continue
    newest=$(find "$d" -maxdepth 1 -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1 || true)
    [[ -z "$newest" ]] && newest=0
    newest_epoch="${newest%.*}"
    if (( newest_epoch < cutoff_epoch )); then
      log "GC: removing stale wal dir $d (newest=${newest_epoch})"
      rm -rf -- "$d"
    fi
  done < <(find "$MA3_BACKUP_DIR/wal" -mindepth 1 -maxdepth 1 -type d)
fi

# 5) Rewrite pitr_manifest.json wal_dirs to drop pruned dirs
if [[ -f "$manifest" ]]; then
  python3 - "$manifest" "$MA3_BACKUP_DIR" <<'PY'
import json, os, sys, tempfile
mpath, root = sys.argv[1], sys.argv[2]
try:
    with open(mpath) as f:
        d = json.load(f)
except Exception:
    sys.exit(0)
old = d.get("wal_dirs") or []
new = []
for w in old:
    p = os.path.join(root, w) if not os.path.isabs(w) else w
    if os.path.isdir(p):
        new.append(w)
if new == old:
    sys.exit(0)
d["wal_dirs"] = new
tmp = mpath + ".tmp"
with open(tmp, "w") as f:
    json.dump(d, f, indent=2)
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp, mpath)
print(f"pruned wal_dirs in pitr_manifest: {len(old) - len(new)} removed", file=sys.stderr)
PY
fi

log "GC done"
