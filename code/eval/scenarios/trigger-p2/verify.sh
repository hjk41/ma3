#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
EVAL_ROOT="$(cd "$D/../.." && pwd)"
exec bash "$EVAL_ROOT/scenarios/compose-network-fix/verify.sh"
