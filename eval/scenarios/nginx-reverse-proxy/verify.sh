#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
curl -sf -m 5 http://127.0.0.1:18080/ | grep -q hello-from-backend
echo verify ok
