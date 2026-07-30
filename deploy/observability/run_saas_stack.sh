#!/usr/bin/env bash
# DEPRECATED: do not run the Prometheus stack on the ma3.io (Aliyun) app host.
# SaaS alerting is the off-host probe on the operator laptop (Phase 0).
# For an optional local lab stack: bash deploy/observability/run_local_stack.sh
set -euo pipefail
echo "REFUSING: run_saas_stack.sh is retired for the app host." >&2
echo "Use off-host probe (ma3-probe.timer) + Feishu on the operator machine." >&2
echo "Optional local lab: bash $(dirname "$0")/run_local_stack.sh" >&2
exit 2
