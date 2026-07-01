#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
curl -sf -m 10 http://127.0.0.1:18081/ | grep -q hello-from-compose-backend
echo verify ok
