#!/usr/bin/env bash
# Archive ma3 operation logs from local disk to CephFS/3FS.

set -euo pipefail
umask 077

: "${MA3_OP_LOG_DIR:=/var/log/ma3/ops}"
: "${MA3_LOG_ARCHIVE_DIR:?MA3_LOG_ARCHIVE_DIR is required}"
: "${MA3_LOG_LOCAL_RETENTION_DAYS:=2}"
: "${MA3_INSTANCE_ID:=unknown-instance}"

export MA3_OP_LOG_DIR MA3_LOG_ARCHIVE_DIR MA3_LOG_LOCAL_RETENTION_DAYS MA3_INSTANCE_ID

python3 - <<'PY'
from app.services.op_log_service import archive_completed_logs
print(archive_completed_logs())
PY

