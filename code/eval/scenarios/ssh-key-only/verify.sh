#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
grep -q '^PasswordAuthentication no' "$D/workspace/sshd_config"
for i in $(seq 1 60); do
  if ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=3 \
    -i "$D/workspace/id_ed25519" -p 18022 eval@127.0.0.1 true 2>/dev/null; then
    echo "verify ok"
    exit 0
  fi
  sleep 1
done
echo "ssh key login failed on :18022"
exit 1
