#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf -- "${tmp}"' EXIT

remote="${tmp}/remote"
release="${remote}/releases/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
mkdir -p "${release}"
cat >"${remote}/ma3.env" <<'EOF'
MA3_DEV_AUTH=0
MA3_INSTANCE_ID=test
MA3_PUBLIC_BASE_URL=https://example.invalid
EOF
printf '%s\n' bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb >"${release}/.ma3-release-commit"

set +e
output="$(bash "${REPO_DIR}/deploy/common/deploy_release_remote.sh" \
  "${remote}" "${release}" git aaaaaaa aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  8000 127.0.0.1 1 1 test https://example.invalid 1 1 0 8000 8001 0 \
  "${remote}/data/upstream.caddy" Y2FkZHkgcmVsb2Fk "" 2>&1)"
status=$?
set -e

test "${status}" -ne 0
grep -q 'release marker does not match' <<<"${output}"

echo "deploy release guard tests passed"
