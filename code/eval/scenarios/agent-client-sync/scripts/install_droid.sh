#!/usr/bin/env bash
# Install Factory Droid CLI into the image (host copy preferred on eval machines).
set -euo pipefail

DEST="${1:-/opt/npm-global/bin/droid}"

if [[ -f /scenario/binaries/droid ]]; then
  install -m 755 /scenario/binaries/droid "${DEST}"
  echo "installed droid from build context binary"
  exit 0
fi

if http_proxy= https_proxy= HTTP_PROXY= HTTPS_PROXY= \
    curl -fsSL https://app.factory.ai/cli | bash; then
  echo "installed droid via factory installer"
  exit 0
fi

if HTTP_PROXY="${HTTP_PROXY:-}" HTTPS_PROXY="${HTTPS_PROXY:-}" \
    npm install -g @factory-ai/cli 2>/dev/null || npm install -g droid 2>/dev/null; then
  echo "installed droid via npm fallback"
  exit 0
fi

echo "FAIL: could not install droid CLI" >&2
exit 1
