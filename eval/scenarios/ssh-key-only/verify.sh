#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
grep -q '^PasswordAuthentication no' "$D/workspace/sshd_config"
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  -i "$D/workspace/id_ed25519" -p 18022 eval@127.0.0.1 true
echo verify ok
