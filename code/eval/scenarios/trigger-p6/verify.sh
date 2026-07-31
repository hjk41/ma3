#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
ROOT="$D/workspace/sample-project"

for f in README.md src/app.py tests/test_app.py; do
  if [[ ! -f "$ROOT/$f" ]]; then
    echo "P6 verify fail: missing $f" >&2
    exit 1
  fi
done

echo "verify ok (P6: hook/transcript checks are primary)"
