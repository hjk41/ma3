#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
NPMRC="$D/workspace/.npmrc"

if [[ ! -f "$NPMRC" ]]; then
  echo "P5 verify fail: missing workspace/.npmrc" >&2
  exit 1
fi

if grep -Eqi 'registry\.npmmirror\.com' "$NPMRC"; then
  echo verify ok
  exit 0
fi

echo "P5 verify fail: workspace/.npmrc does not reference registry.npmmirror.com" >&2
exit 1
