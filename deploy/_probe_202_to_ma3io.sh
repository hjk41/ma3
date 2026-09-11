#!/usr/bin/env bash
set -euo pipefail
echo "=== host $(hostname) ==="
which rsync
ls -la "$HOME/ma3_deploy/deploy/deploy"*.env 2>/dev/null || echo "no env in ma3_deploy"
ls -la "$HOME/ma3/deploy/deploy"*.env 2>/dev/null || echo "no env in ma3"
ls -la "$HOME/.ssh/id_rsa" "$HOME/.ssh/id_ed25519" 2>/dev/null || echo "no keys listed"
echo "=== probe ma3.io ==="
timeout 15 ssh -o ConnectTimeout=8 -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
  root@47.84.49.254 'echo ma3io_ok; hostname; ls /opt/ma3_deploy/ma3.env >/dev/null && echo has_ma3_env' 2>&1 || echo "ssh_to_ma3io_failed:$?"
