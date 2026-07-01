#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$D/workspace"
cp "$D/broken/sshd_config" "$D/workspace/sshd_config"
if [[ ! -f "$D/workspace/id_ed25519" ]]; then
  ssh-keygen -t ed25519 -N "" -f "$D/workspace/id_ed25519" -q
fi
cp "$D/workspace/id_ed25519.pub" "$D/workspace/authorized_keys"
chmod 600 "$D/workspace/authorized_keys"
